import os
from pathlib import Path

import pytest
import pytest_asyncio

from tests._database import get_test_database_url, validate_test_database_url


os.environ["RBB_CONFIG_FILE"] = str(
    Path(__file__).parent / "fixtures" / "test_config.yaml"
)


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run tests that require the dedicated local Postgres test database",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="integration tests require the --integration option"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest_asyncio.fixture
async def test_database():
    from tortoise import Tortoise

    database_url = get_test_database_url()
    validate_test_database_url(database_url)

    try:
        await Tortoise.init(
            db_url=database_url,
            modules={"models": ["rbb_bot.models", "aerich.models"]},
        )
        connection = Tortoise.get_connection("default")
        await connection.execute_script(
            "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
        )
        await Tortoise.generate_schemas(safe=True)
        yield
    finally:
        await Tortoise.close_connections()
