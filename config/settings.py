# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "OutfitAI"
    API_V1_STR: str = "/api/v1"

    # OpenAI API Key - will be loaded from an environment variable
    OPENAI_API_KEY: Optional[str] = None

    # Google Gemini API Key
    GOOGLE_GEMINI_API_KEY: Optional[str] = None

    # Database URL (example for SQLite, we can change this later)
    DATABASE_URL: str = "sqlite:///./outfitai.db"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra='ignore')

settings = Settings()

if __name__ == "__main__":
    print(f"Project Name: {settings.PROJECT_NAME}")
    print(f"OpenAI API Key Loaded: {'Yes' if settings.OPENAI_API_KEY else 'No'}")
    print(f"Google Gemini API Key Loaded: {'Yes' if settings.GOOGLE_GEMINI_API_KEY else 'No'}")
    print(f"Database URL: {settings.DATABASE_URL}")