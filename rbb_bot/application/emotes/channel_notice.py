from rbb_bot.domain.guild_logging import GuildNotice


def emote_channel_notice(channel_id: int, deleted: bool) -> GuildNotice:
    if deleted:
        return GuildNotice(
            key=f"emote-channel-deleted:{channel_id}",
            problem="Could not repost the server's emotes: the emotes channel no longer exists.",
            remedy="Assign a new channel with `/emote post assign`, or stop reposting with `/emote post unassign`.",
            identifiers=(("Channel ID", channel_id),),
        )
    return GuildNotice(
        key=f"emote-channel-forbidden:{channel_id}",
        problem="Could not repost the server's emotes: the bot cannot manage the emotes channel.",
        remedy=(
            f"Give the bot View Channel and Send Messages in <#{channel_id}>, plus Manage Messages "
            "and Read Message History if previous posts are deleted, or assign another channel "
            "with `/emote post assign`."
        ),
        identifiers=(("Channel ID", channel_id),),
    )
