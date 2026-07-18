import pytest

from rbb_bot import container_start, dev_start


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
        ["aerich", "upgrade"],
    ]
    assert exit_info.value.code == (
        container_start.sys.executable,
        [container_start.sys.executable, "./rbb_bot/launcher.py"],
    )


def test_startup_rejects_an_invalid_bootstrap_value(monkeypatch):
    monkeypatch.setenv("AERICH_BOOTSTRAP", "true")

    with pytest.raises(RuntimeError, match="unset or set to 1"):
        container_start.main()


def test_dev_start_uses_local_creds_then_upgrades_before_starting_bot(monkeypatch):
    commands = []
    database_url = "postgres://local-dev-url"

    monkeypatch.delenv("DB_URL", raising=False)
    monkeypatch.setattr(
        dev_start,
        "get_creds",
        lambda: type("Creds", (), {"db_url": database_url})(),
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
    assert commands == [["aerich", "upgrade"]]
    assert exit_info.value.code == (
        dev_start.sys.executable,
        [dev_start.sys.executable, "./rbb_bot/launcher.py"],
    )


def test_dev_start_preserves_an_explicit_database_url(monkeypatch):
    commands = []

    monkeypatch.setenv("DB_URL", "postgres://explicit-url")
    monkeypatch.setattr(
        dev_start,
        "get_creds",
        lambda: pytest.fail("local credentials should not be read"),
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
    assert commands == [["aerich", "upgrade"]]
