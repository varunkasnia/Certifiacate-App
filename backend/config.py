from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
from typing import List, Optional
import json

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Live GenAI Quiz Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./quiz_platform.db"
    
    # AI Configuration (Switched to Gemini)
    GEMINI_API_KEY: str  # <--- MAKE SURE THIS IS IN YOUR .ENV
    OPENAI_API_KEY: Optional[str] = None  # Kept as optional just in case
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://certifiacate-app-frontend-36he.vercel.app",
        "*" 
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return value

        raw = value.strip()
        if not raw:
            return []

        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass

        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    
    # File Upload
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "./uploads"
    
    # Game Settings
    DEFAULT_QUESTION_TIME: int = 30 
    POINTS_CORRECT: int = 1000
    SPEED_BONUS_MAX: int = 500

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Prevents crash if .env has unused keys (like old OpenAI config)


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
