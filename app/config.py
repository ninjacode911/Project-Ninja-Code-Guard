"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration loaded from environment variables."""

    # LLM APIs
    groq_api_key: str = ""
    gemini_api_key: str = ""

    # GitHub App
    github_app_id: str = ""
    github_app_private_key_path: str = "./keys/app.pem"
    github_app_private_key: str = ""  # PEM content directly (for cloud deployment)
    github_webhook_secret: str = ""

    # Database
    database_url: str = ""

    # Redis Cache
    upstash_redis_url: str = ""

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"

    # App Config
    environment: str = "development"
    log_level: str = "INFO"
    confidence_threshold: float = 0.6
    max_repo_files_index: int = 500

    # Security
    dashboard_api_key: str = ""  # Set in production to protect dashboard API
    cors_allowed_origins: str = ""  # Comma-separated origins, e.g. "https://myapp.vercel.app"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
