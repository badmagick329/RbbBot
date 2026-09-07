import os
from pathlib import Path

import yaml
from pydantic import BaseModel, BaseSettings, Field

CONFIG_FILE = Path(
    os.environ.get("RBB_CONFIG_FILE", Path(__file__).parent / "defaults.yaml")
)

ENV_CREDENTIALS = {
    "discord_token": "RBB_DISCORD_TOKEN",
    "db_url": "DB_URL",
    "reddit_id": "RBB_REDDIT_CLIENT_ID",
    "reddit_secret": "RBB_REDDIT_CLIENT_SECRET",
    "reddit_agent": "RBB_REDDIT_USER_AGENT",
    "search_key": "RBB_GOOGLE_SEARCH_KEY",
}

DATA_ENCRYPTION_KEY_ENV = "RBB_DATA_ENCRYPTION_KEY"


class Creds(BaseModel):
    discord_token: str
    db_url: str
    reddit_secret: str
    reddit_id: str
    reddit_agent: str
    search_key: str


class Config(BaseModel):
    debug: bool
    default_prefix: str
    headers: dict
    ig_headers: dict
    kprofiles_url: str
    wiki_url: str
    google_url: str


class DiscordSettings(BaseSettings):
    """Select Discord destinations at startup so the image is environment-independent."""

    owner_id: int = Field(..., gt=0, env="RBB_OWNER_ID")
    logger_channel_id: int = Field(..., gt=0, env="RBB_LOGGER_CHANNEL_ID")
    confirmation_channel_id: int = Field(..., gt=0, env="RBB_CONFIRMATION_CHANNEL_ID")
    confirmation_guild_id: int = Field(..., gt=0, env="RBB_CONFIRMATION_GUILD_ID")


def get_discord_settings() -> DiscordSettings:
    return DiscordSettings()


def get_config():
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)
    for field, variable in (
        ("debug", "RBB_DEBUG"),
        ("default_prefix", "RBB_DEFAULT_PREFIX"),
    ):
        if variable in os.environ:
            config[field] = os.environ[variable]
    return Config(**config)


def get_creds() -> Creds:
    missing = [
        environment_name
        for environment_name in ENV_CREDENTIALS.values()
        if not os.environ.get(environment_name)
    ]
    if missing:
        raise RuntimeError(
            "Missing required credential environment variables: " + ", ".join(missing)
        )

    values = {
        field_name: os.environ[environment_name]
        for field_name, environment_name in ENV_CREDENTIALS.items()
    }
    return Creds(**values)


def get_data_encryption_key() -> str:
    """Return the application data-encryption key without logging it."""
    environment_key = os.environ.get(DATA_ENCRYPTION_KEY_ENV)
    if environment_key:
        return environment_key

    raise RuntimeError(f"Missing required credential: {DATA_ENCRYPTION_KEY_ENV}")


def validate_runtime_settings() -> None:
    """Reject an incomplete deployment before startup can migrate the database."""
    get_config()
    get_creds()
    get_discord_settings()
    get_data_encryption_key()
