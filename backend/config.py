from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List, Optional

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
        "https://yourdomain.vercel.app",
        "*" 
    ]
    
    # File Upload
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "./uploads"
    
    # Game Settings
    DEFAULT_QUESTION_TIME: int = 30 
    POINTS_CORRECT: int = 1000
    SPEED_BONUS_MAX: int = 500
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Prevents crash if .env has unused keys (like old OpenAI config)


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()