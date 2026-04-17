"""
Application configuration — reads from environment / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/macro_tracker"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "dev-secret-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # ── USDA FoodData Central ─────────────────────────────────────────────────
    USDA_API_KEY: str = "DEMO_KEY"
    USDA_BASE_URL: str = "https://api.nal.usda.gov/fdc/v1"

    # ── Anthropic (Vision / OCR) ──────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_VISION_MODEL: str = "claude-3-5-haiku-20241022"

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
