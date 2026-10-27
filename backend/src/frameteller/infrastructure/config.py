"""12-factor settings (CLAUDE.md section 6). Everything environment-specific comes from env vars or .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "staging", "production"]
Effort = Literal["minimal", "low", "medium", "high"]

CONTRIBUTOR_DIRECTOR = "muse-spark-1.3-contributor"
PAID_DIRECTOR = "muse-spark-1.3"


class ConfigError(RuntimeError):
    """Startup configuration is invalid. The message never contains secret values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    model_api_key: SecretStr = Field(min_length=1)
    app_env: AppEnv = "local"
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_realtime_url: str = "wss://api.meta.ai/v1/asr/realtime"

    # Contributor mode trains on inputs: synthetic data only, so never outside local (CLAUDE.md section 5).
    director_model: str | None = None
    image_model: str = "muse-image-1.0"
    sam_model: str = "sam-3.1"
    asr_model: str = "muse-voice-transcribe-1.0"

    director_effort_turn: Effort = "minimal"  # ADR 0002
    director_effort_story: Effort = "low"
    image_panel_size: str = "1536x1024"  # ADR 0003: the Responses image tool rejects 1792x1024
    image_reference_size: str = "1024x1024"
    # Segment on a copy whose longest side is at most this (None = full size); masks are scaled back up.
    sam_max_side: int | None = Field(default=768, ge=256)  # ADR 0007

    budget_per_project_usd: float = Field(default=2.0, gt=0)
    budget_per_day_usd: float = Field(default=10.0, gt=0)

    text_timeout_s: float = Field(default=60, gt=0)
    image_timeout_s: float = Field(default=120, gt=0)
    sam_timeout_s: float = Field(default=60, gt=0)
    retry_attempts: int = Field(default=3, ge=1, le=6)
    breaker_failures: int = Field(default=5, ge=1)
    breaker_cooldown_s: float = Field(default=30, gt=0)

    local_storage_dir: Path = Path(".data")
    allowed_origins: str = ""  # comma-separated browser origins for CORS and WebSocket Origin checks
    log_level: str = "INFO"

    rate_limit_per_minute: int = Field(default=120, ge=1)  # per client IP, all endpoints
    rate_limit_costly_per_minute: int = Field(default=20, ge=1)  # endpoints that spend model credits

    @field_validator("sam_max_side", mode="before")
    @classmethod
    def _empty_means_full_size(cls, value: object) -> object:
        return None if isinstance(value, str) and value.strip().lower() in ("", "none") else value

    @model_validator(mode="after")
    def _director_for_env(self) -> Settings:
        if self.director_model is None:
            self.director_model = CONTRIBUTOR_DIRECTOR if self.app_env == "local" else PAID_DIRECTOR
        if self.app_env != "local" and self.director_model.endswith("-contributor"):
            raise ValueError("contributor models are for synthetic local data only, not staging or production")
        return self

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def director(self) -> str:
        assert self.director_model is not None  # set by the validator
        return self.director_model


def load_settings(**overrides: object) -> Settings:
    """Validate configuration at startup and fail fast with a readable message (no values echoed)."""
    try:
        return Settings(**overrides)  # type: ignore[arg-type]
    except ValidationError as e:
        problems = []
        for err in e.errors(include_input=False, include_url=False):
            field = ".".join(str(p) for p in err["loc"]) or "settings"
            if field == "model_api_key" and err["type"] in {"missing", "string_too_short"}:
                problems.append("MODEL_API_KEY is not set. Put it in .env (local) or the environment's secrets.")
            else:
                problems.append(f"{field.upper()}: {err['msg']}")
        raise ConfigError("Invalid configuration:\n- " + "\n- ".join(problems)) from None
