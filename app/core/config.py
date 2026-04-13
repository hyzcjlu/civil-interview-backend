"""Central configuration loaded from .env"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")

    # LLM
    qwen_api_key: str = os.getenv("QWEN_API_KEY", "")
    qwen_base_url: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen-plus")

    # Database (MySQL or SQLite fallback)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./civil_interview.db")


settings = Settings()
