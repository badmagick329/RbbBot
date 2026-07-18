"""Development startup: apply local migrations, then launch the bot."""

import os
import subprocess
import sys

from rbb_bot.settings.config import get_creds


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    """Use the local development database unless DB_URL is explicitly supplied."""
    if not os.environ.get("DB_URL"):
        os.environ["DB_URL"] = get_creds().db_url

    run_command(["aerich", "upgrade"])
    os.execv(sys.executable, [sys.executable, "./rbb_bot/launcher.py"])


if __name__ == "__main__":
    main()
