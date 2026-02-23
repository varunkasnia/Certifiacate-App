import google.generativeai as genai
import json
from config import settings
from schemas import QuestionSchema, AIGeneratedQuestions
import logging

logger = logging.getLogger("uvicorn")

genai.configure(api_key=settings.GEMINI_API_KEY)

MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.5-pro",
    "gemini-flash-latest"
]

QUIZ_JSON_SCHEMA = """
{
    "questions": [
        {
            "question_text": "The actual question text?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Option A",
            "explanation": "Why this answer is correct",
            "time_limit": 30
        }
    ]
}
"""

def generate_with_fallback(prompt: str, difficulty: str, context_len: int = 0) -> AIGeneratedQuestions:
    last_error = None

    for model_name in MODELS_TO_TRY:
        try:
            logger.info(f"🤖 Attempting to generate quiz using model: {model_name}")
            
            model = genai.GenerativeModel(
                model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            
            response = model.generate_content(prompt)
            text_response = response.text.strip()
            
            if text_response.startswith("```json"):
                text_response = text_response[7:-3]
            elif text_response.startswith("```"):
                text_response = text_response[3:-3]

            data = json.loads(text_response)
            validated_questions = [QuestionSchema(**q) for q in data["questions"]]
            
            logger.info(f"✅ Success with model: {model_name}")
            
            return AIGeneratedQuestions(
                questions=validated_questions,
                metadata={
                    "model": model_name,
                    "difficulty": difficulty,
                    "content_length": context_len
                }
            )

        except Exception as e:
            logger.warning(f"⚠️ Model {model_name} failed: {str(e)}")
            last_error = e
            continue

    error_msg = f"All AI models failed. Please check your API key quota. Last error: {str(last_error)}"
    logger.error(error_msg)
    raise Exception(error_msg)


def generate_quiz_from_text(content: str, num_questions: int = 10, difficulty: str = "medium") -> AIGeneratedQuestions:
    prompt = f"""
    You are an expert quiz creator. Analyze the content and generate {num_questions} multiple-choice questions.
    Difficulty: {difficulty}
    
    Content: "{content[:15000]}"
    
    Requirements:
    1. 4 options per question.
    2. One correct answer (must match one of the options exactly).
    3. JSON Format:
    {QUIZ_JSON_SCHEMA}
    """
    return generate_with_fallback(prompt, difficulty, len(content))


def generate_quiz_from_topic(topic: str, num_questions: int = 10, difficulty: str = "medium") -> AIGeneratedQuestions:
    prompt = f"""
    You are an expert quiz creator. Generate {num_questions} multiple-choice questions about: "{topic}".
    Difficulty: {difficulty}
    
    Requirements:
    1. Questions must be factually accurate.
    2. 4 options per question.
    3. One correct answer.
    4. JSON Format:
    {QUIZ_JSON_SCHEMA}
    """
    return generate_with_fallback(prompt, difficulty)
