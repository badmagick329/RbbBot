from pathlib import Path

import yaml
from pydantic import BaseModel

CONFIG_FILE = Path(__file__).parent / "config.yaml"
CREDS_FILE = Path(__file__).parent / "creds.yaml"


class Creds(BaseModel):
    discord_token: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str
    db_url: str
    reddit_secret: str
    reddit_id: str
    reddit_agent: str
    twitter_key: str
    twitter_secret: str
    twitter_token: str
    twitter_token_secret: str
    ig_app: str
    ig_cookies: dict
    search_key: str
    rapid_api_key: str


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


def get_creds():
    with open(CREDS_FILE, "r") as f:
        creds = yaml.safe_load(f)
    return Creds(**creds)
