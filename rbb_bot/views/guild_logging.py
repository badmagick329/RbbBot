from io import BytesIO

import discord
from rbb_bot.core.formatted_timestamps import MemberTimestamps, MessageTimestamps
from rbb_bot.settings.const import MAX_EMBED_FIELD_VALUE


def logging_settings(settings):
    embed = discord.Embed(title="Logging settings")
    embed.add_field(
        name="Channel",
        value=f"<#{settings.channel_id}>" if settings.channel_id else "Disabled",
        inline=False,
    )
    for field in ("member_join", "member_leave", "message_removed", "message_edited"):
        embed.add_field(
            name=field.replace("_", " ").title(),
            value="Enabled" if getattr(settings, field) else "Disabled",
        )
    return embed


def message_event(before, after=None):
    message = after or before
    embed = discord.Embed(
        title="Message Edited" if after else "Message Deleted",
        color=discord.Color.orange() if after else discord.Color.red(),
    )
    embed.set_author(
        name=f"{before.author.name}({before.author.id})",
        icon_url=before.author.display_avatar.url,
    )
    embed.add_field(name="Channel", value=before.channel.mention)
    embed.add_field(name="Message ID", value=str(before.id))
    embed.add_field(
        name="Created at", value=MessageTimestamps(message).created, inline=False
    )
    contents = (
        [("Before", before.content), ("After", after.content)]
        if after
        else [("Content", before.content)]
    )
    long_content = any(len(content) > MAX_EMBED_FIELD_VALUE for _, content in contents)
    if long_content:
        embed.add_field(
            name="Content", value="Message content is attached as a file.", inline=False
        )
        text = "\n\n".join(f"{label}:\n{content}" for label, content in contents)
        return {
            "embed": embed,
            "file": discord.File(
                BytesIO(text.encode("utf-8")), filename=f"message_{before.id}.txt"
            ),
        }
    for label, content in contents:
        embed.add_field(name=label, value=content or "No content", inline=False)
    return {"embed": embed}


def member_event(member, joined):
    timestamps = MemberTimestamps(member)
    embed = discord.Embed(
        title="Member Joined" if joined else "Member Left",
        color=discord.Color.green() if joined else discord.Color.red(),
    )
    embed.set_author(
        name=f"{member.name}({member.id})", icon_url=member.display_avatar.url
    )
    embed.add_field(
        name="Account Created",
        value=f"{timestamps.account_created} ~ {timestamps.account_created_relative}",
    )
    if not joined:
        embed.add_field(
            name="Joined At",
            value=f"{timestamps.joined_at} ~ {timestamps.joined_at_relative}"
            if member.joined_at
            else "Unknown",
        )
    return {"embed": embed}
