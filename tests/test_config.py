import pytest
from pydantic import ValidationError

from foodanalyzer.config import Settings


def test_settings_defaults_are_student_friendly():
    settings = Settings()
    assert settings.nutrition_cache_ttl_seconds == 86400
    assert settings.max_concurrency == 10
    assert settings.max_image_size_mb == 5
    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_log_level_is_normalized():
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValidationError):
        Settings(log_level="loud")


def test_openrouter_settings_can_be_configured():
    settings = Settings(
        llm_provider="openrouter",
        llm_model="nvidia/nemotron-3-super-120b-a12b:free",
        openrouter_api_key="test-key",
        openrouter_reasoning_enabled=True,
        openrouter_reasoning_exclude=True,
    )
    assert settings.llm_provider == "openrouter"
    assert settings.openrouter_api_key == "test-key"
    assert settings.openrouter_reasoning_enabled is True