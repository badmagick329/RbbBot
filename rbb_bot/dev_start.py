"""Development startup: apply local migrations, then launch the bot."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from rbb_bot.settings.config import validate_runtime_settings


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    """Load development settings only in this explicit local entry point."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    validate_runtime_settings()

    run_command([sys.executable, "-m", "rbb_bot.upgrade_database"])
    os.execv(sys.executable, [sys.executable, "-m", "rbb_bot.launcher"])


if __name__ == "__main__":
    main()
