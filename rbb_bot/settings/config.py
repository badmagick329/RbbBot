import os
from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_FILE = Path(
    os.environ.get("RBB_CONFIG_FILE", Path(__file__).parent / "config.yaml")
)
DEFAULT_CREDS_FILE = Path(__file__).parent / "creds.yaml"

ENV_CREDENTIALS = {
    "discord_token": "RBB_DISCORD_TOKEN",
    "db_url": "DB_URL",
    "reddit_id": "RBB_REDDIT_CLIENT_ID",
    "reddit_secret": "RBB_REDDIT_CLIENT_SECRET",
    "reddit_agent": "RBB_REDDIT_USER_AGENT",
    "search_key": "RBB_GOOGLE_SEARCH_KEY",
}


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


def get_config():
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)
    return Config(**config)


def _creds_file() -> Path:
    return Path(os.environ.get("RBB_CREDS_FILE", DEFAULT_CREDS_FILE))


def _get_environment_creds() -> Creds:
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


def get_creds():
    creds_file = _creds_file()
    if creds_file.exists():
        with open(creds_file, "r") as f:
            creds = yaml.safe_load(f)
        return Creds(**creds)

    return _get_environment_creds()
