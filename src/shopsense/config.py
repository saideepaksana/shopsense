import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    refund_ceiling_minor: int = 500000
    return_window_days: int = 10
    extended_window_days: int = 15
    refund_limit_count: int = 3
    refund_limit_days: int = 90
    clause_top_k: int = 6
    llm_retries: int = 2
    max_replans: int = 1
    baseline_max_steps: int = 8
    db_path: str = str(PROJECT_ROOT / "data" / "shopsense.db")
    policy_path: str = str(PROJECT_ROOT / "policies" / "store_policy.md")
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_json_mode: bool = True
    llm_temperature: float = 0
    llm_min_interval_seconds: float = 0
    llm_timeout_seconds: float = 60


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    def value(name: str, default: str = "") -> str:
        return os.getenv(name, default)

    db_path = Path(value("SHOPSENSE_DB", str(PROJECT_ROOT / "data" / "shopsense.db")))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return Settings(
        db_path=str(db_path),
        llm_base_url=value("LLM_BASE_URL"),
        llm_api_key=value("LLM_API_KEY"),
        llm_model=value("LLM_MODEL"),
        llm_json_mode=value("LLM_JSON_MODE", "true").lower() == "true",
        llm_temperature=float(value("LLM_TEMPERATURE", "0")),
        llm_min_interval_seconds=float(value("LLM_MIN_INTERVAL_SECONDS", "0")),
        llm_timeout_seconds=float(value("LLM_TIMEOUT_SECONDS", "60")),
    )
