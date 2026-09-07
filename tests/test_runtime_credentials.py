import pytest
from pydantic import ValidationError
from rbb_bot.settings.config import (
    ENV_CREDENTIALS,
    get_creds,
    get_data_encryption_key,
    get_discord_settings,
    get_config,
)


def test_environment_credentials_ignore_legacy_file(monkeypatch, tmp_path):
    legacy = tmp_path / "creds.yaml"
    legacy.write_text("discord_token: unwanted-token")
    monkeypatch.setenv("RBB_CREDS_FILE", str(legacy))
    for field, variable in ENV_CREDENTIALS.items():
        monkeypatch.setenv(variable, f"value-for-{field}")
    assert get_creds().discord_token == "value-for-discord_token"


def test_missing_credentials_report_names_without_values(monkeypatch):
    for variable in ENV_CREDENTIALS.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("RBB_DISCORD_TOKEN", "private-token")
    with pytest.raises(RuntimeError) as error:
        get_creds()
    assert "DB_URL" in str(error.value)
    assert "private-token" not in str(error.value)


def test_encryption_key_requires_explicit_environment(monkeypatch):
    monkeypatch.delenv("RBB_DATA_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RBB_DATA_ENCRYPTION_KEY"):
        get_data_encryption_key()


def test_discord_destinations_and_config_follow_runtime_environment(monkeypatch):
    for variable in (
        "RBB_OWNER_ID",
        "RBB_LOGGER_CHANNEL_ID",
        "RBB_CONFIRMATION_CHANNEL_ID",
        "RBB_CONFIRMATION_GUILD_ID",
    ):
        monkeypatch.setenv(variable, "123")
    assert get_discord_settings().confirmation_channel_id == 123
    monkeypatch.setenv("RBB_OWNER_ID", "0")
    with pytest.raises(ValidationError):
        get_discord_settings()
    monkeypatch.setenv("RBB_DEBUG", "false")
    monkeypatch.setenv("RBB_DEFAULT_PREFIX", "?")
    assert get_config().debug is False
    assert get_config().default_prefix == "?"
