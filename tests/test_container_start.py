import pytest

from rbb_bot import container_start


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
