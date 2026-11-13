"""Confirmation posts for source submissions in the central confirmation channel."""

import discord

from rbb_bot.application.sources.contracts import PublishedPost, ReactionsRejected
from rbb_bot.settings.const import BotEmojis
from rbb_bot.views.sources import confirmation_post, submitter_id

DELETED_MARK = "DELETED"


async def _channel(bot, channel_id):
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    return channel


class DiscordConfirmationPosts:
    """One submission's view of the confirmation channel.

    Built per submission: it keeps the messages it published so the use case can retract
    or react to them by ID without fetching them again.
    """

    def __init__(self, bot, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self._messages = {}

    async def publish(self, submission):
        channel = await _channel(self.bot, self.channel_id)
        message = await channel.send(confirmation_post(submission))
        self._messages[message.id] = message
        return PublishedPost(message.id, message.jump_url)

    async def retract(self, post_id):
        await self._messages.pop(post_id).delete()

    async def open_for_moderation(self, post_id):
        message = self._messages[post_id]
        try:
            await message.add_reaction(BotEmojis.CROSS)
            await message.add_reaction(BotEmojis.HAMMER)
        except discord.HTTPException as error:
            raise ReactionsRejected(post_id) from error


class DiscordConfirmationPost:
    """The confirmation post one moderation reaction arrived on.

    Built per reaction event and fetched once, so the hammer's blacklist and removal read
    the same message.
    """

    def __init__(self, bot, channel_id: int, message_id: int):
        self.bot = bot
        self.channel_id = channel_id
        self.id = message_id
        self._message = None

    async def _fetch(self):
        if self._message is None:
            channel = await _channel(self.bot, self.channel_id)
            self._message = await channel.fetch_message(self.id)
        return self._message

    async def from_bot(self):
        return (await self._fetch()).author.id == self.bot.user.id

    async def submitter_id(self):
        return submitter_id((await self._fetch()).content)

    async def mark_deleted(self):
        message = await self._fetch()
        if not message.content.rstrip().endswith(f"\n{DELETED_MARK}"):
            await message.edit(content=f"{message.content}\n\n{DELETED_MARK}")


class SourceConfirmationService:
    """Delete the confirmation posts of submissions about to be erased.

    Shared by privacy deletion and guild cleanup, which both keep the database rows until
    every post is gone, since the rows are the only way to find the posts again.
    """

    def __init__(self, bot):
        self.bot = bot

    async def delete_confirmation_messages(
        self, source_entries: list, *, scope: str, scope_id: int
    ) -> bool:
        """Delete every confirmation post, treating already-missing posts as deleted."""
        for source_entry in source_entries:
            try:
                channel = await _channel(self.bot, source_entry.conf_channel_id)
                message = await channel.fetch_message(source_entry.conf_message_id)
                await message.delete()
            except discord.NotFound:
                continue
            except (discord.Forbidden, discord.HTTPException):
                self.bot.logger.exception(
                    "Source confirmation deletion failed scope=%s scope_id=%s "
                    "source_entry_count=%s",
                    scope,
                    scope_id,
                    len(source_entries),
                )
                return False
        return True
