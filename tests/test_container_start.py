import pytest

from rbb_bot import container_start, dev_start


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    monkeypatch.setattr(container_start, "validate_runtime_settings", lambda: None)
    monkeypatch.setattr(dev_start, "validate_runtime_settings", lambda: None)


def test_startup_bootstraps_then_upgrades_before_starting_bot(monkeypatch):
    commands = []

    monkeypatch.setenv("AERICH_BOOTSTRAP", "1")
    monkeypatch.setattr(container_start, "run_command", commands.append)
    monkeypatch.setattr(
        container_start.os,
        "execv",
        lambda executable, args: (_ for _ in ()).throw(SystemExit((executable, args))),
    )

    with pytest.raises(SystemExit) as exit_info:
        container_start.main()

    assert commands == [
        [container_start.sys.executable, "-m", "rbb_bot.migration_bootstrap"],
        [container_start.sys.executable, "-m", "rbb_bot.data_encryption_preflight"],
        ["aerich", "upgrade"],
        [container_start.sys.executable, "-m", "rbb_bot.data_encryption_migration"],
    ]
    assert exit_info.value.code == (
        container_start.sys.executable,
        [container_start.sys.executable, "./rbb_bot/launcher.py"],
    )


def test_startup_rejects_an_invalid_bootstrap_value(monkeypatch):
    monkeypatch.setenv("AERICH_BOOTSTRAP", "true")

    with pytest.raises(RuntimeError, match="unset or set to 1"):
        container_start.main()


def test_incomplete_runtime_settings_prevent_migrations(monkeypatch):
    monkeypatch.delenv("AERICH_BOOTSTRAP", raising=False)
    def missing_settings():
        raise RuntimeError("Missing runtime settings")
    monkeypatch.setattr(container_start, "validate_runtime_settings", missing_settings)
    monkeypatch.setattr(container_start, "run_command", lambda command: pytest.fail("Must not migrate"))
    with pytest.raises(RuntimeError, match="Missing runtime settings"):
        container_start.main()


def test_dev_start_uses_local_creds_then_upgrades_before_starting_bot(monkeypatch):
    commands = []
    database_url = "postgres://local-dev-url"

    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.setattr(
        dev_start,
        "load_dotenv",
        lambda path, override: monkeypatch.setenv("DB_URL", database_url),
    )
    monkeypatch.setattr(dev_start, "run_command", commands.append)
    monkeypatch.setattr(
        dev_start.os,
        "execv",
        lambda executable, args: (_ for _ in ()).throw(SystemExit((executable, args))),
    )

    with pytest.raises(SystemExit) as exit_info:
        dev_start.main()

    assert dev_start.os.environ["DB_URL"] == database_url
    assert commands == [
        [dev_start.sys.executable, "-m", "rbb_bot.data_encryption_preflight"],
        ["aerich", "upgrade"],
        [dev_start.sys.executable, "-m", "rbb_bot.data_encryption_migration"],
    ]
    assert exit_info.value.code == (
        dev_start.sys.executable,
        [dev_start.sys.executable, "./rbb_bot/launcher.py"],
    )


def test_dev_start_preserves_an_explicit_database_url(monkeypatch):
    commands = []

    monkeypatch.setenv("DB_URL", "postgres://explicit-url")
    monkeypatch.setattr(
        dev_start,
        "load_dotenv",
        lambda path, override: None,
    )
    monkeypatch.setattr(dev_start, "run_command", commands.append)
    monkeypatch.setattr(
        dev_start.os,
        "execv",
        lambda executable, args: (_ for _ in ()).throw(SystemExit((executable, args))),
    )

    with pytest.raises(SystemExit):
        dev_start.main()

    assert dev_start.os.environ["DB_URL"] == "postgres://explicit-url"
    assert commands == [
        [dev_start.sys.executable, "-m", "rbb_bot.data_encryption_preflight"],
        ["aerich", "upgrade"],
        [dev_start.sys.executable, "-m", "rbb_bot.data_encryption_migration"],
    ]
