"""Container startup: optionally baseline once, migrate, then run the bot."""

import os
import subprocess
import sys


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    bootstrap = os.environ.get("AERICH_BOOTSTRAP", "")
    if bootstrap not in {"", "1"}:
        raise RuntimeError("AERICH_BOOTSTRAP must be unset or set to 1")

    if bootstrap == "1":
        run_command([sys.executable, "-m", "rbb_bot.migration_bootstrap"])

    run_command(["aerich", "upgrade"])
    os.execv(sys.executable, [sys.executable, "./rbb_bot/launcher.py"])


if __name__ == "__main__":
    main()
