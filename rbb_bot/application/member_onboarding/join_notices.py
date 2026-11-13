from rbb_bot.application.member_onboarding.contracts import (
    AutoRolesRejected,
    JoinChannelUnavailable,
)
from rbb_bot.application.member_onboarding.handle_member_join import (
    MemberJoinAction,
    MemberJoinFailure,
)
from rbb_bot.domain.guild_logging import GuildNotice
from rbb_bot.domain.member_onboarding.configuration import (
    MissingManageRoles,
    UnassignableAutoRoles,
)

# action: (what is posted, permissions it needs, assign command, disable command)
_CHANNELS = {
    MemberJoinAction.GREETING: (
        "greeting",
        "View Channel, Send Messages and Embed Links",
        "/greet enable",
        "/greet disable",
    ),
    MemberJoinAction.JOIN_RESPONSE: (
        "welcome message",
        "View Channel and Send Messages",
        "/welcome channel",
        "/welcome disable",
    ),
}


def _role_mentions(role_ids):
    return ", ".join(f"<@&{role_id}>" for role_id in role_ids)


def join_failure_notice(
    failure: MemberJoinFailure, member_id: int
) -> GuildNotice | None:
    """Turn a join failure into a guild notice when the guild's own setup caused it.

    Anything else (bugs, Discord outages, a member leaving mid-join) returns None and
    stays in the operational log, since guild administrators cannot act on it.
    """
    error = failure.error
    member = ("Member ID", member_id)

    if isinstance(error, JoinChannelUnavailable) and failure.action in _CHANNELS:
        name, permissions, assign, disable = _CHANNELS[failure.action]
        channel = ("Channel ID", error.channel_id)
        kind = failure.action.value
        if error.deleted:
            return GuildNotice(
                key=f"{kind}-channel-deleted:{error.channel_id}",
                problem=f"Could not post the {name} for a new member: the {name} channel no longer exists.",
                remedy=f"Choose a new channel with `{assign}`, or turn this off with `{disable}`.",
                identifiers=(member, channel),
            )
        return GuildNotice(
            key=f"{kind}-channel-forbidden:{error.channel_id}",
            problem=f"Could not post the {name} for a new member: the bot cannot post in the {name} channel.",
            remedy=f"Give the bot {permissions} in <#{error.channel_id}>, or choose another channel with `{assign}`.",
            identifiers=(member, channel),
        )

    if isinstance(error, MissingManageRoles):
        return GuildNotice(
            key="auto-roles-manage-roles",
            problem="Could not give auto roles to a new member: the bot lacks the Manage Roles permission.",
            remedy="Give the bot's role the Manage Roles permission, or clear auto roles with `/autorole remove_all`.",
            identifiers=(member,),
        )

    if isinstance(error, UnassignableAutoRoles):
        roles = tuple(("Role ID", role_id) for role_id in error.role_ids)
        return GuildNotice(
            key=f"auto-roles-unassignable:{sorted(error.role_ids)}",
            problem="Skipped auto roles the bot cannot assign to a new member.",
            remedy=(
                "Give the bot the Manage Roles permission and move its highest role above "
                f"{_role_mentions(error.role_ids)}, or remove them with `/autorole remove`. "
                "Roles managed by an integration can never be assigned."
            ),
            identifiers=(member, *roles),
        )

    if isinstance(error, AutoRolesRejected):
        roles = tuple(("Role ID", role_id) for role_id in error.role_ids)
        if error.deleted:
            return GuildNotice(
                key=f"auto-roles-deleted:{sorted(error.role_ids)}",
                problem="Could not give auto roles to a new member: an auto role no longer exists.",
                remedy="Run `/autorole list` to drop deleted roles from the auto role list.",
                identifiers=(member, *roles),
            )
        return GuildNotice(
            key=f"auto-roles-rejected:{sorted(error.role_ids)}",
            problem="Could not give auto roles to a new member: Discord refused the role change.",
            remedy=(
                "Give the bot the Manage Roles permission and move its highest role above "
                f"{_role_mentions(error.role_ids)}, or remove them with `/autorole remove`."
            ),
            identifiers=(member, *roles),
        )

    return None
