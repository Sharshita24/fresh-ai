"""Runtime settings, read once from the environment (and .env)."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL") or "sqlite:///./freshchain.db"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_timeout_ms: int = int(os.getenv("GEMINI_TIMEOUT_MS", "15000"))
    monitor_interval_s: int = int(os.getenv("MONITOR_INTERVAL_SECONDS", "300"))
    auto_execute: bool = _bool("AUTO_EXECUTE", False)
    seed_demo_data: bool = _bool("SEED_DEMO_DATA", True)
    home_store_id: str = os.getenv("HOME_STORE_ID", "store-042")
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )
    webhook_url: str = os.getenv("WEBHOOK_URL", "").strip()
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    export_dir: str = os.getenv("EXPORT_DIR", "exports")
    bigquery_dataset: str = os.getenv("BIGQUERY_DATASET", "").strip()

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
