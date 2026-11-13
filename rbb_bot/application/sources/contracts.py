from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol


@dataclass(frozen=True)
class Submitter:
    """The stored user behind a source submission.

    `cached_username` is the name stored at their first submission, not their current one;
    confirmation posts and `source find` show it.
    """

    id: int
    cached_username: str | None
    blacklisted: bool


@dataclass(frozen=True)
class SourceRequest:
    """A `source add` or `source edit` invocation as the requester typed it."""

    emote: str
    source_url: str | None
    event: str | None
    source_date: str | None
    guild_id: int
    channel_id: int
    message_id: int
    jump_url: str
    submitter_id: int
    submitter_name: str


@dataclass(frozen=True)
class SourceDetails:
    """The fields a submitter confirms and `source find` reports."""

    source_url: str | None
    event: str | None
    source_date: date | None


@dataclass(frozen=True)
class SourceSubmission:
    emote: str
    emote_url: str
    details: SourceDetails
    guild_id: int
    channel_id: int
    message_id: int
    jump_url: str
    submitter: Submitter


@dataclass(frozen=True)
class RecordedSource:
    details: SourceDetails
    submitter_id: int
    submitter_name: str | None


@dataclass(frozen=True)
class SubmitterTally:
    submitter_id: int
    cached_username: str | None
    submissions: int


@dataclass(frozen=True)
class PublishedPost:
    """A confirmation post as the record stores it: the ID moderation reactions arrive on."""

    id: int
    jump_url: str


class Refusal(Enum):
    BLACKLISTED = "blacklisted"
    ALREADY_EXISTS = "already_exists"
    URL_TOO_LONG = "url_too_long"
    EVENT_TOO_LONG = "event_too_long"
    MISSING_URL = "missing_url"
    INVALID_URL = "invalid_url"
    INVALID_DATE = "invalid_date"
    NOTHING_TO_EDIT = "nothing_to_edit"
    UNVERIFIED_EMOTE = "unverified_emote"


class SourceRefused(Exception):
    """A submission the feature turns down for a reason the requester can act on."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.value)
        self.refusal = refusal


class ReactionsRejected(Exception):
    """Discord refused the moderation reactions on a confirmation post.

    The Discord adapter raises this in place of Discord's own error, chained to it, so the
    use case can keep a recorded submission whose post merely lacks its reactions.
    """

    def __init__(self, post_id: int):
        super().__init__(f"post_id={post_id}")
        self.post_id = post_id


class SourceRepository(Protocol):
    async def register_submitter(self, user_id: int, username: str) -> Submitter:
        """Create the user on first submission; cache `username` only when none is stored."""

    async def exists(self, emote: str) -> bool: ...

    async def record(
        self, submission: SourceSubmission, post: PublishedPost
    ) -> None: ...

    async def sources(self, emote: str) -> tuple[RecordedSource, ...]:
        """Every submission for the emote, oldest confirmation post first."""

    async def tallies(self) -> tuple[SubmitterTally, ...]: ...

    async def forget(self, post_id: int) -> None: ...

    async def blacklisted(self, user_id: int) -> bool | None:
        """None when the user has no stored record."""

    async def blacklist(self, user_id: int) -> None: ...

    async def lift_blacklist(self, user_id: int) -> bool:
        """Return whether a source blacklist entry was removed."""


class EmoteImages(Protocol):
    async def url(self, emote: str) -> str | None:
        """The emote's image URL, or None when the text is no emote or Discord lacks it."""


class ConfirmationPosts(Protocol):
    """The confirmation channel, where every submission is posted for moderation."""

    async def publish(self, submission: SourceSubmission) -> PublishedPost: ...

    async def retract(self, post_id: int) -> None: ...

    async def open_for_moderation(self, post_id: int) -> None:
        """Add the moderation reactions; raise `ReactionsRejected` when Discord refuses."""


class ConfirmationPost(Protocol):
    """One confirmation post a moderation reaction arrived on."""

    id: int

    async def from_bot(self) -> bool: ...

    async def submitter_id(self) -> int | None:
        """The submitter the post names, or None when it names none or several."""

    async def mark_deleted(self) -> None: ...


class OperationalLogger(Protocol):
    def info(self, msg: str, *args, **kwargs) -> None: ...

    def exception(self, msg: str, *args, **kwargs) -> None: ...
