"""12-factor settings (CLAUDE.md section 6). Everything environment-specific comes from env vars or .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from frameteller.application.budget import BudgetCalendar, parse_days
from frameteller.application.capacity import CapacityLimits
from frameteller.application.limits import DemoLimits

AppEnv = Literal["local", "staging", "production"]
StorageBackend = Literal["local", "blob"]
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
    # The global daily cap across every project: past it, "The studio is full for today". Days are dates at
    # BUDGET_UTC_OFFSET_HOURS (the team's UTC+4); BUDGET_DAYS_USD raises the cap on launch and judging days.
    budget_per_day_usd: float = Field(default=10.0, gt=0)
    budget_days_usd: str = "2026-11-02:25,2026-11-05:25,2026-11-06:25,2026-11-07:25,2026-11-08:25"
    budget_utc_offset_hours: float = Field(default=4, ge=-12, le=14)

    # The judge pass: a private link (/judge#<JUDGE_TOKEN>) sets a signed cookie. Judges skip the per-visitor
    # caps and the waiting room, and spend from their own reserved pool. Rotate by changing the token.
    judge_token: SecretStr | None = None
    # Each browser that opens the link gets its own pass, limited to JUDGE_STORIES_PER_PASS_PER_DAY new stories.
    # The judges' reserve is JUDGE_BUDGET_PER_DAY_USD, raised on judging days by JUDGE_BUDGET_DAYS_USD; the admin
    # page can lower it without a redeploy.
    judge_budget_per_day_usd: float = Field(default=15.0, ge=0)
    judge_budget_days_usd: str = "2026-11-05:25,2026-11-06:25,2026-11-07:25,2026-11-08:25"
    judge_stories_per_pass_per_day: int = Field(default=15, ge=1)
    judge_pass_days: int = Field(default=21, ge=1, le=60)
    # Judges wake Muse Glimmer (ADR 0020), when REVIEWER is screen or fallback: at most this many wake-ups a day,
    # and this much estimated Modal spend for them (GPU time at GLIMMER_USD_PER_HOUR). Past either: Spark only.
    judge_glimmer_wakes_per_day: int = Field(default=10, ge=0)
    judge_glimmer_usd_per_day: float = Field(default=5.0, ge=0)
    judge_glimmer_idle_minutes: float = Field(default=5, gt=0, le=30)  # the lease ends this long after a judge
    glimmer_usd_per_hour: float = Field(default=3.95, ge=0)  # Modal H100
    # The gallery's admin page: /admin#<ADMIN_TOKEN>, sent as a bearer token. Unset: no admin API.
    admin_token: SecretStr | None = None

    # Global concurrency (ADR 0016): past these, work waits in line with its place and an estimate.
    capacity_sessions: int = Field(default=24, ge=1)  # live voice sessions and readings
    capacity_images: int = Field(default=8, ge=1)  # Muse Image calls in flight
    capacity_sam: int = Field(default=4, ge=1)  # SAM calls in flight
    capacity_exports: int = Field(default=2, ge=1)  # animatic renders (ffmpeg), in their own queue
    capacity_jobs: int = Field(default=32, ge=1)  # background jobs running at once (they mostly wait on models)

    # Public-demo guardrails (production defaults). A visitor is a hash of IP and browser id.
    limit_projects_per_visitor_per_day: int = Field(default=3, ge=1)
    # More stories per visitor on the dates named ("date:stories", days at UTC+4): the judging days.
    limit_projects_per_visitor_days: str = "2026-11-05:5,2026-11-06:5,2026-11-07:5,2026-11-08:5"
    limit_narration_minutes_per_session: float = Field(default=3, gt=0)
    limit_shots_per_episode: int = Field(default=12, ge=1)
    limit_renders_per_project: int = Field(default=60, ge=1)  # panel renders and edits
    limit_episodes_per_script: int = Field(default=3, ge=1)
    limit_script_characters: int = Field(default=4000, ge=100)
    limit_speech_characters_per_visitor_per_day: int = Field(default=12_000, ge=0)  # Text-to-Speech
    limit_exports_per_project: int = Field(default=3, ge=1)
    # The kill switch: a friendly "back soon" page everywhere but shared storyboards. Set with
    # `az containerapp update --set-env-vars DEMO_PAUSED=true` (a new revision, no redeploy; docs/runbook.md).
    demo_paused: bool = False

    # Continuity supervisor (ADR 0012, 0013). reviewer: "spark" (the director's model: paid outside local),
    # "glimmer" (our Modal endpoint only), "fallback" (Glimmer first, Spark when Glimmer is cold, slow or down)
    # or "screen" (as fallback, and Spark confirms whatever Glimmer flags: the eval's choice when Glimmer is on).
    reviewer: Literal["spark", "glimmer", "fallback", "screen"] = "spark"
    reviewer_effort: Effort = "low"
    glimmer_base_url: str = ""  # https://<workspace>--frameteller-glimmer-serve.modal.run/v1
    glimmer_api_key: SecretStr | None = None  # the endpoint's bearer token, never the Meta key
    glimmer_model: str = "muse-glimmer"
    glimmer_timeout_s: float = Field(default=20, gt=0)  # past this (a cold start), Spark reviews instead
    # fallback and screen use Glimmer only while the warm-up script holds a lease, so visitors never wake the GPU.
    glimmer_only_when_warm: bool = True
    rubrics_dir: Path | None = None  # agents/; found next to the repo when unset

    # "Read it to me" (ADR 0015): Azure AI Speech Text-to-Speech, with a key (the resource is outside our tenant).
    azure_speech_key: SecretStr | None = None
    azure_speech_region: str = "eastus2"
    speech_timeout_s: float = Field(default=30, gt=0)
    speech_characters_per_day: int = Field(default=200_000, ge=0)  # all visitors together

    text_timeout_s: float = Field(default=60, gt=0)
    image_timeout_s: float = Field(default=120, gt=0)
    sam_timeout_s: float = Field(default=60, gt=0)
    retry_attempts: int = Field(default=3, ge=1, le=6)
    breaker_failures: int = Field(default=5, ge=1)
    breaker_cooldown_s: float = Field(default=30, gt=0)

    # Where media, project documents and the spend ledger live. Container disk is ephemeral: blob in Azure.
    storage_backend: StorageBackend = "local"
    local_storage_dir: Path = Path(".data")
    azure_storage_account: str = ""  # with DefaultAzureCredential (managed identity in Azure, az login locally)
    azure_storage_connection_string: SecretStr | None = None  # the Azurite emulator only
    azure_storage_api_version: str | None = None  # pin an older API version for Azurite
    azure_media_container: str = "media"
    azure_projects_container: str = "projects"
    allowed_origins: str = ""  # comma-separated browser origins for CORS and WebSocket Origin checks
    public_app_url: str = ""  # the studio, where share links send browsers; default: the first https origin
    log_level: str = "INFO"

    rate_limit_per_minute: int = Field(default=120, ge=1)  # per client IP, all endpoints
    rate_limit_costly_per_minute: int = Field(default=20, ge=1)  # endpoints that spend model credits

    @field_validator("sam_max_side", mode="before")
    @classmethod
    def _empty_means_full_size(cls, value: object) -> object:
        return None if isinstance(value, str) and value.strip().lower() in ("", "none") else value

    @field_validator(
        "azure_storage_connection_string",
        "azure_storage_api_version",
        "glimmer_api_key",
        "rubrics_dir",
        "azure_speech_key",
        "judge_token",
        "admin_token",
        mode="before",
    )
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("budget_days_usd", "judge_budget_days_usd", "limit_projects_per_visitor_days")
    @classmethod
    def _days_parse(cls, value: str) -> str:
        parse_days(value)  # ValueError: "BUDGET_DAYS_USD: ..." at startup
        return value

    @field_validator("judge_token", "admin_token")
    @classmethod
    def _long_tokens(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("needs at least 32 characters (make one with secrets.token_urlsafe(32))")
        return value

    @model_validator(mode="after")
    def _director_for_env(self) -> Settings:
        if self.director_model is None:
            self.director_model = CONTRIBUTOR_DIRECTOR if self.app_env == "local" else PAID_DIRECTOR
        if self.app_env != "local" and self.director_model.endswith("-contributor"):
            raise ValueError("contributor models are for synthetic local data only, not staging or production")
        return self

    @model_validator(mode="after")
    def _glimmer_needs_an_endpoint(self) -> Settings:
        if self.reviewer != "spark" and not (self.glimmer_base_url.strip() and self.glimmer_api_key):
            raise ValueError(f"REVIEWER={self.reviewer} needs GLIMMER_BASE_URL and GLIMMER_API_KEY")
        return self

    @model_validator(mode="after")
    def _blob_needs_an_account(self) -> Settings:
        if self.storage_backend == "blob" and not (self.azure_storage_account or self.azure_storage_connection_string):
            raise ValueError("STORAGE_BACKEND=blob needs AZURE_STORAGE_ACCOUNT (or a connection string for Azurite)")
        return self

    @property
    def azure_speech_tts_base_url(self) -> str:
        return f"https://{self.azure_speech_region.strip()}.tts.speech.microsoft.com"

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def app_url(self) -> str:
        if self.public_app_url.strip():
            return self.public_app_url.strip().rstrip("/")
        return next((o for o in self.origins if o.startswith("https://")), "")

    @property
    def demo_limits(self) -> DemoLimits:
        return DemoLimits(
            projects_per_visitor_per_day=self.limit_projects_per_visitor_per_day,
            narration_ms_per_session=round(self.limit_narration_minutes_per_session * 60_000),
            shots_per_episode=self.limit_shots_per_episode,
            renders_per_project=self.limit_renders_per_project,
            exports_per_project=self.limit_exports_per_project,
            episodes_per_script=self.limit_episodes_per_script,
            script_characters=self.limit_script_characters,
            speech_characters_per_visitor_per_day=self.limit_speech_characters_per_visitor_per_day,
            projects_per_visitor_days={d: int(n) for d, n in parse_days(self.limit_projects_per_visitor_days).items()},
            stories_per_judge_pass_per_day=self.judge_stories_per_pass_per_day,
        )

    @property
    def budget_calendar(self) -> BudgetCalendar:
        return BudgetCalendar(
            per_day_usd=self.budget_per_day_usd,
            judge_per_day_usd=self.judge_budget_per_day_usd if self.judge_token else 0.0,
            days_usd=parse_days(self.budget_days_usd),
            utc_offset_hours=self.budget_utc_offset_hours,
            judge_days_usd=parse_days(self.judge_budget_days_usd),
        )

    @property
    def capacity_limits(self) -> CapacityLimits:
        return CapacityLimits(
            sessions=self.capacity_sessions,
            images=self.capacity_images,
            sam=self.capacity_sam,
            exports=self.capacity_exports,
        )

    @property
    def rubrics_path(self) -> Path:
        """agents/: RUBRICS_DIR in the container image, else the repo's own folder (local runs and tests)."""
        if self.rubrics_dir is not None:
            return self.rubrics_dir
        return Path(__file__).resolve().parents[4] / "agents"  # backend/src/frameteller/infrastructure -> repo

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
