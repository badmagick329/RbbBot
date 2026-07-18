from aerich_test_config import DB_CONFIG
from tests._database import get_test_database_url


def test_aerich_config_uses_the_dedicated_test_database():
    assert DB_CONFIG["connections"]["default"] == get_test_database_url()
    assert DB_CONFIG["apps"]["models"]["models"] == [
        "rbb_bot.models",
        "aerich.models",
    ]
