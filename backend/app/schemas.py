from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class QuestionOption(BaseModel):
    id: str = Field(..., min_length=1, max_length=5)
    text: str = Field(..., min_length=1, max_length=300)


class QuizQuestion(BaseModel):
    question: str = Field(..., min_length=5, max_length=600)
    options: list[QuestionOption] = Field(..., min_length=2, max_length=6)
    correct_option_id: str = Field(..., min_length=1, max_length=5)
    time_limit_seconds: int = Field(..., ge=5, le=90)

    @field_validator("correct_option_id")
    @classmethod
    def validate_correct_option(cls, value: str, info):
        options = info.data.get("options", [])
        option_ids = {option.id for option in options}
        if value not in option_ids:
            raise ValueError("correct_option_id must be one of the option ids")
        return value


class QuizGenerationResponse(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    questions: list[QuizQuestion] = Field(..., min_length=3, max_length=25)


class QuizGenerateRequest(BaseModel):
    topic_prompt: str = Field(..., min_length=3, max_length=2000)
    question_count: int = Field(default=5, ge=3, le=20)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    topic_prompt: str = Field(default="", max_length=2000)
    source_text: str = Field(default="", max_length=20000)
    questions: list[QuizQuestion] = Field(..., min_length=1, max_length=50)


class QuizResponse(BaseModel):
    id: str
    title: str
    topic_prompt: str
    source_text: str
    questions: list[QuizQuestion]
    created_at: datetime


class StartSessionRequest(BaseModel):
    quiz_id: str
    host_name: str = Field(..., min_length=2, max_length=40)


class SessionResponse(BaseModel):
    id: str
    pin: str
    host_name: str
    quiz_id: str
    status: str
    current_question_index: int
    created_at: datetime


class JoinRoomPayload(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)
    player_name: str = Field(..., min_length=2, max_length=40)


class SubmitAnswerPayload(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)
    question_index: int = Field(..., ge=0)
    selected_option_id: str = Field(..., min_length=1, max_length=5)


class LeaderboardEntry(BaseModel):
    player_id: str
    player_name: str
    score: int
    correct_answers: int


class ErrorResponse(BaseModel):
    detail: str
