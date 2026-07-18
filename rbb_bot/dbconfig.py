"""Aerich configuration for container and deployment commands."""

import os


database_url = os.environ.get("DB_URL")
if not database_url:
    raise RuntimeError("DB_URL is required to run Aerich")


DB_CONFIG = {
    "connections": {"default": database_url},
    "apps": {
        "models": {
            "models": ["rbb_bot.models", "aerich.models"],
            "default_connection": "default",
        }
    },
    "timezone": "UTC",
}
