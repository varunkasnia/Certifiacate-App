from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


class QuestionSchema(BaseModel):
    question_text: str = Field(..., min_length=5)
    options: List[str] = Field(..., min_items=2, max_items=6)
    correct_answer: str
    time_limit: int = Field(default=30, ge=5, le=120)


class QuizCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    created_by: str = Field(..., min_length=1, max_length=100)
    questions: List[QuestionSchema]


class QuizResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    created_by: str
    created_at: datetime
    question_count: int

    class Config:
        from_attributes = True


class QuestionResponse(BaseModel):
    id: int
    question_text: str
    options: List[str]
    correct_answer: str
    time_limit: int
    order: int

    class Config:
        from_attributes = True


class AIGenerateRequest(BaseModel):
    topic: Optional[str] = None
    file_content: Optional[str] = None
    num_questions: int = Field(default=10, ge=3, le=50)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    
    @validator('topic', 'file_content')
    def check_at_least_one_source(cls, v, values):
        # At least one of topic or file_content must be provided
        # This is checked in the route, so we just pass through here
        return v


class AIGeneratedQuestions(BaseModel):
    questions: List[QuestionSchema]
    metadata: Optional[dict] = None


class GameSessionCreate(BaseModel):
    quiz_id: int
    host_name: str = Field(..., min_length=1, max_length=100)


class GameSessionResponse(BaseModel):
    id: int
    quiz_id: int
    pin: str
    host_name: str
    status: str
    current_question_index: int
    created_at: datetime
    player_count: int

    class Config:
        from_attributes = True


class PlayerJoinRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    pin: str = Field(..., min_length=6, max_length=6)
    roll_number: str = Field(..., min_length=1, max_length=50)


class PlayerResponse(BaseModel):
    id: int
    name: str
    roll_number: Optional[str] = None
    score: int
    joined_at: datetime

    class Config:
        from_attributes = True


class SubmitAnswerRequest(BaseModel):
    player_id: int
    question_id: int
    answer: str
    time_taken: float = Field(..., ge=0)


class LeaderboardEntry(BaseModel):
    player_id: int
    name: str
    score: int
    correct_answers: int
    total_questions: int


class GameStateUpdate(BaseModel):
    type: str  # "player_joined", "game_started", "question_changed", "game_ended"
    data: dict


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(..., pattern="^(host|joiner)$")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    # Make role optional with a default value so it stops failing validation!
    role: Optional[str] = Field(default="host", pattern="^(host|joiner)$")

class AuthUserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
