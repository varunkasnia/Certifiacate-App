from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Live GenAI Quiz Platform"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./quiz.db"
    gemini_api_key: str = ""
    gemini_models: str = "gemini-2.5-flash,gemini-2.0-flash,gemini-2.0-flash-001,gemini-2.5-pro,gemini-flash-latest"
    cors_origins: str = "http://localhost:3000"
    host_secret: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def gemini_model_list(self) -> list[str]:
        return [model.strip() for model in self.gemini_models.split(",") if model.strip()]


settings = Settings()
