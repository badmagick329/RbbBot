"""Safe, test-only Aerich configuration.

This module must never be used for deployment.  It only permits the dedicated
local Postgres database used by the integration test harness.
"""

import os
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_TEST_DATABASE_URL = "postgres://rbb_test:rbb_test@127.0.0.1:5433/rbb_test"

os.environ.setdefault(
    "RBB_CONFIG_FILE", str(Path(__file__).parent / "tests" / "fixtures" / "test_config.yaml")
)

database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
parsed = urlparse(database_url)

try:
    database_port = parsed.port
except ValueError as exc:
    raise ValueError("TEST_DATABASE_URL has an invalid port") from exc

if not (
    parsed.scheme in {"postgres", "postgresql"}
    and parsed.hostname in {"127.0.0.1", "localhost"}
    and database_port == 5433
    and parsed.path == "/rbb_test"
    and parsed.username == "rbb_test"
    and parsed.password == "rbb_test"
):
    raise ValueError(
        "TEST_DATABASE_URL must target the dedicated local rbb_test database "
        "on localhost:5433"
    )

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
