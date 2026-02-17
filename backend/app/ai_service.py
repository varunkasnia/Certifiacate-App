import json
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.schemas import QuizGenerationResponse


class GeminiService:
    def __init__(self) -> None:
        self._client = None
        if settings.gemini_api_key:
            self._client = genai.Client(api_key=settings.gemini_api_key)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _assert_client(self) -> genai.Client:
        if not self._client:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        return self._client

    def _build_generation_prompt(self, topic_prompt: str, source_text: str, question_count: int, difficulty: str) -> str:
        src = source_text[:12000] if source_text else ""
        return (
            "You are a quiz generation engine. Return ONLY strict JSON matching the schema. "
            f"Generate exactly {question_count} multiple-choice questions. "
            f"Difficulty: {difficulty}.\n"
            "Rules:\n"
            "1) Every question must have 4 options with ids A,B,C,D\n"
            "2) correct_option_id must be one of option ids\n"
            "3) time_limit_seconds between 10 and 60\n"
            "4) Avoid duplicate questions\n"
            "5) Keep options concise\n\n"
            f"Topic prompt:\n{topic_prompt}\n\n"
            f"Reference source text (optional):\n{src}"
        )

    def generate_quiz(self, topic_prompt: str, source_text: str, question_count: int, difficulty: str) -> QuizGenerationResponse:
        client = self._assert_client()
        prompt = self._build_generation_prompt(topic_prompt, source_text, question_count, difficulty)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuizGenerationResponse,
            temperature=0.4,
        )

        last_error: Exception | None = None
        for model in settings.gemini_model_list:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                text = response.text or ""
                payload: Any = json.loads(text)
                return QuizGenerationResponse.model_validate(payload)
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(f"Gemini generation failed across all models: {last_error}")

    def extract_text_from_image(self, image_bytes: bytes, mime_type: str = "image/png") -> str:
        client = self._assert_client()
        instruction = (
            "Extract all useful quiz-relevant text and facts from this image. "
            "Return plain text only."
        )

        last_error: Exception | None = None
        for model in settings.gemini_model_list:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        instruction,
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    ],
                )
                return (response.text or "").strip()
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(f"Gemini image parsing failed across all models: {last_error}")


gemini_service = GeminiService()
