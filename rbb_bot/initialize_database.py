"""Explicit provisioning command; normal startup never creates a schema."""

import argparse
import asyncio

from dotenv import load_dotenv
from tortoise import Tortoise

from rbb_bot.infrastructure.database.lifecycle import initialize_empty_database


async def initialize() -> None:
    from rbb_bot.dbconfig import DB_CONFIG

    await Tortoise.init(config=DB_CONFIG)
    try:
        await initialize_empty_database()
    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        help="Explicit local settings file; process variables take precedence",
    )
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    asyncio.run(initialize())


if __name__ == "__main__":
    main()
