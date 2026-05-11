from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Documentation RAG"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/documentation_rag"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    upload_dir: Path = _REPO_ROOT / "data" / "uploads"


settings = Settings()
