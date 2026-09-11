"""Container startup: optionally baseline once, migrate, then run the bot."""

import os
import subprocess
import sys

from rbb_bot.settings.config import validate_runtime_settings


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    bootstrap = os.environ.get("AERICH_BOOTSTRAP", "")
    if bootstrap not in {"", "1"}:
        raise RuntimeError("AERICH_BOOTSTRAP must be unset or set to 1")

    validate_runtime_settings()

    if bootstrap == "1":
        run_command([sys.executable, "-m", "rbb_bot.migration_bootstrap"])

    run_command([sys.executable, "-m", "rbb_bot.upgrade_database"])
    os.execv(sys.executable, [sys.executable, "-m", "rbb_bot.launcher"])


if __name__ == "__main__":
    main()
