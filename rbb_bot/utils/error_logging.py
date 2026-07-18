from discord.ext.commands import Context


def format_error_context(ctx: Context) -> str:
    """Return operational error context without command input or message data."""
    details = []
    if ctx.guild:
        details.append(f"guild_id={ctx.guild.id}")
    if ctx.command:
        details.append(f"command={ctx.command.qualified_name}")
    return " ".join(details)
