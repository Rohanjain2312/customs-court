"""Single configuration module. Everything reads settings from here."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Price(BaseModel):
    """USD per million tokens."""

    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float
    batch_discount: float = 0.5  # batch price = list price * batch_discount


# Checked 2026-09-28 against platform.claude.com/docs/en/about-claude/models/overview
# and the pricing page. Cache writes are 1.25x (5 min) and 2x (1 h) of base input,
# cache reads 0.1x. Batch requests are 50% off and the discount applies on top of
# cache multipliers (pricing page, "Batch processing" section).
# OpenAI prices checked 2026-09-28 against platform.openai.com/docs/pricing.
PRICES: dict[str, Price] = {
    # Main reasoner from 2026-09-29 on. Same list price as Sonnet 5.5 and the cheapest
    # Sonnet per token (Sonnet 4.6 and 4.5 are $3/$15). Kept 5.5 for older ledger rows.
    "claude-sonnet-5": Price(input=2.0, output=10.0, cache_write_5m=2.5, cache_write_1h=4.0, cache_read=0.2),
    "claude-sonnet-5-5": Price(
        input=2.0, output=10.0, cache_write_5m=2.5, cache_write_1h=4.0, cache_read=0.2
    ),
    "claude-haiku-4-5": Price(input=1.0, output=5.0, cache_write_5m=1.25, cache_write_1h=2.0, cache_read=0.1),
    "claude-haiku-4-5-20251001": Price(
        input=1.0, output=5.0, cache_write_5m=1.25, cache_write_1h=2.0, cache_read=0.1
    ),
    "gpt-5-mini": Price(input=0.25, output=2.0, cache_write_5m=0.25, cache_write_1h=0.25, cache_read=0.025),
    "gpt-5-nano": Price(input=0.05, output=0.4, cache_write_5m=0.05, cache_write_1h=0.05, cache_read=0.005),
    # Open-weights models run on this machine with llama.cpp. Free.
    "local-": Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0),
    # Mistral free "Experiment" plan (no charges; rate-limited).
    "mistral-": Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0),
    "ministral-": Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0),
    "magistral-": Price(input=0.0, output=0.0, cache_write_5m=0.0, cache_write_1h=0.0, cache_read=0.0),
}

FORBIDDEN_MODEL_MARKERS = ("opus", "fable", "mythos")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    hf_token: str | None = None

    reasoner_model: str = "claude-sonnet-5"
    advocate_model: str = "claude-haiku-4-5"
    judge_model: str = "claude-haiku-4-5"
    openai_model: str = "gpt-5-mini"

    # Local open-weights models: model id -> OpenAI-compatible endpoint of its llama-server.
    local_endpoints: str = (
        "local-qwen3.5-4b=http://127.0.0.1:8081/v1,local-qwen3.5-2b=http://127.0.0.1:8082/v1"
    )
    local_temperature: float = 0.7
    # Mistral free "Experiment" plan: requests per second and sampling.
    mistral_api_key: str | None = None
    mistral_rps: float = 1.0
    mistral_temperature: float = 0.3
    # Per-thread read-only DB connections for tools (used by the high-concurrency GPU job).
    tools_parallel: bool = False
    local_thinking: bool = False

    def local_endpoint(self, model: str) -> str:
        pairs = dict(x.split("=", 1) for x in self.local_endpoints.split(",") if "=" in x)
        if model not in pairs:
            raise KeyError(f"No LOCAL_ENDPOINTS entry for {model}")
        return pairs[model]

    budget_usd_total: float = 40.0
    budget_usd_per_run: float = 8.0
    budget_usd_per_day: float = 20.0
    demo_session_cap_usd: float = 2.0

    data_dir: Path = ROOT / "data"
    # Offline mode: only serve responses from the on-disk cache, never call an API.
    offline: bool = False
    phase: str = "dev"
    redact_eval: bool = False
    # Turn off the local embedding model (tests and CI use BM25 only).
    use_vectors: bool = True
    # Max characters of corpus text a tool returns in one call.
    tool_text_limit: int = 6000

    # The ledger always lives in the main data dir so every dollar is counted,
    # even when tests point DATA_DIR at fixture data.
    ledger_file: Path = ROOT / "data" / "ledger.jsonl"
    cache_dir_override: Path | None = None

    @property
    def ledger_path(self) -> Path:
        return self.ledger_file

    @property
    def cache_dir(self) -> Path:
        return self.cache_dir_override or (self.data_dir / "cache")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tariffagent.sqlite"

    def check_models(self) -> None:
        for m in (self.reasoner_model, self.advocate_model, self.judge_model):
            if any(x in m.lower() for x in FORBIDDEN_MODEL_MARKERS):
                raise ValueError(f"Model {m} is not allowed by the money rules (no Opus or Fable class).")

    def fingerprint(self) -> str:
        """Hash of the settings that change results. Secrets are excluded."""
        keep = {
            k: str(v)
            for k, v in self.model_dump().items()
            if not k.endswith("_key") and k not in {"hf_token", "data_dir", "phase"}
        }
        return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:12]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.check_models()
    return s


def price_for(model: str) -> Price:
    if model in PRICES:
        return PRICES[model]
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    raise KeyError(f"No price for model {model}. Add it to config.PRICES before calling it.")
