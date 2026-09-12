import re
from dataclasses import dataclass

MAX_TRIGGER = 200
MAX_RESPONSE = 2000


class TagInputError(ValueError):
    pass


@dataclass(frozen=True)
class TagResponse:
    id: int
    content: str


@dataclass(frozen=True)
class TagDefinition:
    id: int
    trigger: str
    inline: bool
    responses: tuple[TagResponse, ...]
    use_count: int = 0


@dataclass(frozen=True)
class GuildTags:
    emojis_channel_id: int | None
    tags: tuple[TagDefinition, ...]


def normalize_trigger(value: str) -> str:
    value = value.lower().strip()
    if not value:
        raise TagInputError("Trigger can't be empty")
    if len(value) > MAX_TRIGGER:
        raise TagInputError(f"Trigger can't be longer than {MAX_TRIGGER} characters")
    return value


def normalize_response(value: str) -> str:
    value = value.strip()
    if not value:
        raise TagInputError("Response can't be empty")
    if len(value) > MAX_RESPONSE:
        raise TagInputError(f"Response can't be longer than {MAX_RESPONSE} characters")
    return value


def match_tag(tags: tuple[TagDefinition, ...], message: str) -> TagDefinition | None:
    """Exact tags take precedence; inline triggers are literals bounded by non-word characters."""
    normalized = message.lower().strip()
    for tag in tags:
        if tag.responses and not tag.inline and tag.trigger == normalized:
            return tag
    for tag in tags:
        if (
            tag.responses
            and tag.inline
            and re.search(rf"(?<!\w){re.escape(tag.trigger)}(?!\w)", normalized)
        ):
            return tag
    return None
