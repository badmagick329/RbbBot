from abc import ABC

import discord


class FormattedTimestamps(ABC):
    created: str
    created_relative: str

    def __init__(self) -> None:
        raise NotImplementedError(
            "This class is not meant to be instantiated directly."
        )


class MemberTimestamps(FormattedTimestamps):
    joined_at: str | None
    joined_at_relative: str | None

    def __init__(self, member: discord.Member) -> None:
        created_timestamp = int(member.created_at.timestamp())
        joined_at_timestamp = (
            int(member.joined_at.timestamp()) if member.joined_at else None
        )

        self.account_created = f"<t:{created_timestamp}:f>"
        self.account_created_relative = f"<t:{created_timestamp}:R>"
        if joined_at_timestamp:
            self.joined_at = f"<t:{joined_at_timestamp}:f>"
            self.joined_at_relative = f"<t:{joined_at_timestamp}:R>"


class MessageTimestamps(FormattedTimestamps):
    edited_at: str | None
    edited_at_relative: str | None

    def __init__(self, message: discord.Message) -> None:
        created_timestamp = int(message.created_at.timestamp())
        self.created = f"<t:{created_timestamp}:f>"
        self.created_relative = f"<t:{created_timestamp}:R>"

        if message.edited_at:
            edited_timestamp = int(message.edited_at.timestamp())
            self.edited_at = f"<t:{edited_timestamp}:f>"
            self.edited_at_relative = f"<t:{edited_timestamp}:R>"
