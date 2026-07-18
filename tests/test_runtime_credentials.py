import pytest

from rbb_bot.settings.config import ENV_CREDENTIALS, get_creds


def test_get_creds_reads_local_file(monkeypatch, tmp_path):
    creds_file = tmp_path / "creds.yaml"
    creds_file.write_text(
        "\n".join(
            [
                "discord_token: local-token",
                "db_url: postgres://local",
                "reddit_id: local-reddit-id",
                "reddit_secret: local-reddit-secret",
                "reddit_agent: local-agent",
                "search_key: local-search-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RBB_CREDS_FILE", str(creds_file))

    creds = get_creds()

    assert creds.discord_token == "local-token"
    assert creds.db_url == "postgres://local"


def test_get_creds_reads_environment_when_file_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("RBB_CREDS_FILE", str(tmp_path / "missing.yaml"))
    for field_name, environment_name in ENV_CREDENTIALS.items():
        monkeypatch.setenv(environment_name, f"value-for-{field_name}")

    creds = get_creds()

    assert creds.discord_token == "value-for-discord_token"
    assert creds.search_key == "value-for-search_key"


def test_get_creds_reports_missing_environment_variable_names(monkeypatch, tmp_path):
    monkeypatch.setenv("RBB_CREDS_FILE", str(tmp_path / "missing.yaml"))
    for environment_name in ENV_CREDENTIALS.values():
        monkeypatch.delenv(environment_name, raising=False)

    with pytest.raises(RuntimeError) as error:
        get_creds()

    assert "RBB_DISCORD_TOKEN" in str(error.value)
    assert "credential environment variables" in str(error.value)
