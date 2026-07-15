import os
from urllib.parse import urlparse

DEFAULT_TEST_DATABASE_URL = "postgres://rbb_test:rbb_test@127.0.0.1:5433/rbb_test"


def get_test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def validate_test_database_url(database_url: str) -> None:
    parsed = urlparse(database_url)

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("TEST_DATABASE_URL has an invalid port") from exc

    is_safe = (
        parsed.scheme in {"postgres", "postgresql"}
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and port == 5433
        and parsed.path == "/rbb_test"
        and parsed.username == "rbb_test"
        and parsed.password == "rbb_test"
    )
    if not is_safe:
        raise ValueError(
            "TEST_DATABASE_URL must target the dedicated local rbb_test database "
            "on localhost:5433"
        )
