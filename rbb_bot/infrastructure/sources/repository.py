from rbb_bot.application.sources.contracts import (
    PublishedPost,
    RecordedSource,
    SourceDetails,
    SourceSubmission,
    Submitter,
    SubmitterTally,
)
from rbb_bot.infrastructure.encryption.codec import get_data_encryption_service
from rbb_bot.models import DiscordUser, SourceEntry

# `DiscordUser.blacklist` is a JSON object shared by features; this one owns one key.
BLACKLIST_KEY = "source"
BLACKLISTED = "blacklist"


def _lookup(emote: str) -> str:
    return get_data_encryption_service().lookup_token(emote)


def _is_blacklisted(blacklist) -> bool:
    return bool(blacklist) and blacklist.get(BLACKLIST_KEY) == BLACKLISTED


class TortoiseSourceRepository:
    """Keep source submissions on `SourceEntry` rows and submitters on `DiscordUser` rows.

    Emote strings are encrypted, so lookups by emote go through their HMAC lookup token.
    Blacklist writes name their column and keep keys other features own.
    """

    async def register_submitter(self, user_id: int, username: str) -> Submitter:
        user, _ = await DiscordUser.get_or_create(
            id=user_id, defaults={"cached_username": username}
        )
        if not user.cached_username:
            user.cached_username = username
            await user.save(update_fields=["cached_username_ciphertext"])
        return Submitter(user.id, user.cached_username, _is_blacklisted(user.blacklist))

    async def exists(self, emote: str) -> bool:
        return await SourceEntry.filter(emoji_lookup=_lookup(emote)).exists()

    async def record(self, submission: SourceSubmission, post: PublishedPost) -> None:
        user = await DiscordUser.get(id=submission.submitter.id)
        await SourceEntry.create(
            emoji_string=submission.emote,
            emoji_url=submission.emote_url,
            source_url=submission.details.source_url,
            source_date=submission.details.source_date,
            event=submission.details.event,
            guild_id=submission.guild_id,
            channel_id=submission.channel_id,
            message_id=submission.message_id,
            jump_url=submission.jump_url,
            user=user,
            conf_message_id=post.id,
            conf_jump_url=post.jump_url,
        )

    async def sources(self, emote: str) -> tuple[RecordedSource, ...]:
        rows = (
            await SourceEntry.filter(emoji_lookup=_lookup(emote))
            .order_by("conf_message_id")
            .prefetch_related("user")
        )
        return tuple(
            RecordedSource(
                SourceDetails(row.source_url, row.event, row.source_date),
                row.user.id,
                row.user.cached_username,
            )
            for row in rows
        )

    async def tallies(self) -> tuple[SubmitterTally, ...]:
        rows = await SourceEntry.all().order_by("id").prefetch_related("user")
        users = {}
        counts = {}
        for row in rows:
            users.setdefault(row.user.id, row.user)
            counts[row.user.id] = counts.get(row.user.id, 0) + 1
        return tuple(
            SubmitterTally(user_id, users[user_id].cached_username, count)
            for user_id, count in counts.items()
        )

    async def forget(self, post_id: int) -> None:
        row = await SourceEntry.filter(conf_message_id=post_id).first()
        if row is not None:
            await row.delete()

    async def blacklisted(self, user_id: int) -> bool | None:
        user = await DiscordUser.get_or_none(id=user_id)
        if user is None:
            return None
        return _is_blacklisted(user.blacklist)

    async def blacklist(self, user_id: int) -> None:
        user = await DiscordUser.get(id=user_id)
        user.blacklist = {**(user.blacklist or {}), BLACKLIST_KEY: BLACKLISTED}
        await user.save(update_fields=["blacklist_ciphertext"])

    async def lift_blacklist(self, user_id: int) -> bool:
        user = await DiscordUser.get_or_none(id=user_id)
        if user is None or BLACKLIST_KEY not in (user.blacklist or {}):
            return False
        blacklist = dict(user.blacklist)
        blacklist.pop(BLACKLIST_KEY)
        user.blacklist = blacklist
        await user.save(update_fields=["blacklist_ciphertext"])
        return True
