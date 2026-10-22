"""Settings from environment variables, so the same image runs as a demo, with OpenAI or with a self-hosted model."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # "demo": rule-based, no language model (free, deterministic)
    # "openai": OpenAI API; "local": any OpenAI-compatible server (Ollama, vLLM, LM Studio) at LLM_BASE_URL
    llm_provider: str = os.getenv("LLM_PROVIDER", "demo")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    db_path: str = os.getenv("DB_PATH", ":memory:")
    timezone: str = os.getenv("TZ_NAME", "Europe/Berlin")
    # cost guard for public demos with a real model
    session_limit_per_hour: int = int(os.getenv("SESSION_LIMIT_PER_HOUR", "25"))
    global_limit_per_day: int = int(os.getenv("GLOBAL_LIMIT_PER_DAY", "400"))
    seats: int = 40
    walk_in_reserve: int = 10
    max_group: int = 12


settings = Settings()
