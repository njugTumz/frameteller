import pytest

from frameteller.infrastructure.config import ConfigError, load_settings

FAKE_KEY = "LLM_test_not_a_real_key_000000"


@pytest.fixture(autouse=True)
def _no_env_files(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """Settings must come only from what each test passes, never from a developer's .env."""
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    for name in ("MODEL_API_KEY", "APP_ENV", "DIRECTOR_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_missing_key_fails_fast_with_a_clear_message() -> None:
    with pytest.raises(ConfigError, match="MODEL_API_KEY is not set"):
        load_settings()


def test_key_is_secret_and_never_in_repr() -> None:
    s = load_settings(model_api_key=FAKE_KEY)
    assert FAKE_KEY not in repr(s)
    assert FAKE_KEY not in str(s.model_dump())
    assert s.model_api_key.get_secret_value() == FAKE_KEY


def test_local_defaults() -> None:
    s = load_settings(model_api_key=FAKE_KEY)
    assert s.app_env == "local"
    assert s.director == "muse-spark-1.3-contributor"
    assert (s.director_effort_turn, s.director_effort_story) == ("minimal", "low")
    assert s.image_panel_size == "1536x1024"


@pytest.mark.parametrize("env", ["staging", "production"])
def test_paid_director_outside_local(env: str) -> None:
    assert load_settings(model_api_key=FAKE_KEY, app_env=env).director == "muse-spark-1.3"


def test_contributor_model_is_refused_outside_local() -> None:
    with pytest.raises(ConfigError, match="contributor models are for synthetic local data only"):
        load_settings(model_api_key=FAKE_KEY, app_env="production", director_model="muse-spark-1.3-contributor")


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", FAKE_KEY)
    monkeypatch.setenv("BUDGET_PER_DAY_USD", "3.5")
    assert load_settings().budget_per_day_usd == 3.5


def test_invalid_values_are_reported_without_echoing_them() -> None:
    with pytest.raises(ConfigError) as e:
        load_settings(model_api_key=FAKE_KEY, app_env="moon", budget_per_day_usd=-1)
    assert "APP_ENV" in str(e.value)
    assert "BUDGET_PER_DAY_USD" in str(e.value)
    assert "moon" not in str(e.value)


def test_sam_downscale_defaults_to_768_and_empty_means_full_size(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load_settings(model_api_key=FAKE_KEY).sam_max_side == 768
    monkeypatch.setenv("SAM_MAX_SIDE", "")
    assert load_settings(model_api_key=FAKE_KEY).sam_max_side is None
