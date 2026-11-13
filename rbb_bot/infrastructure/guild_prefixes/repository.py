from rbb_bot.models import Guild


class TortoiseGuildPrefixRepository:
    """Keep a guild's prefix on its `Guild` row.

    Unlike other features' settings, reading the prefix creates the row: the `prefix`
    command has always made the guild a configured guild, even when it only shows the
    prefix. Writes name their column so a concurrent change to another feature's settings
    on the same row survives.
    """

    async def prefix(self, guild_id: int) -> str:
        guild, _ = await Guild.get_or_create(id=guild_id)
        return guild.prefix

    async def set_prefix(self, guild_id: int, prefix: str) -> None:
        guild, _ = await Guild.get_or_create(id=guild_id)
        guild.prefix = prefix
        await guild.save(update_fields=["prefix_ciphertext"])

    async def all_prefixes(self) -> dict[int, str]:
        return {guild.id: guild.prefix for guild in await Guild.all()}
