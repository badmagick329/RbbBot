import pytest

from tests._database import DEFAULT_TEST_DATABASE_URL, validate_test_database_url


def test_default_database_url_is_safe():
    validate_test_database_url(DEFAULT_TEST_DATABASE_URL)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgres://rbb_test:rbb_test@db.example.com:5433/rbb_test",
        "postgres://rbb_test:rbb_test@127.0.0.1:5432/rbb_test",
        "postgres://rbb_test:rbb_test@127.0.0.1:5433/rbb_bot",
        "postgres://developer:password@127.0.0.1:5433/rbb_test",
    ],
)
def test_unsafe_database_urls_are_rejected(database_url):
    with pytest.raises(ValueError, match="dedicated local rbb_test"):
        validate_test_database_url(database_url)
