from rbb_bot.application.guild_prefixes.contracts import PrefixRefused, Refusal
from rbb_bot.domain.guild_prefixes import MAX_PREFIX_LENGTH


def refusal_reply(refusal: PrefixRefused, prefix: str) -> str:
    if refusal.refusal is Refusal.TOO_LONG:
        return f"Prefix must be less than {MAX_PREFIX_LENGTH} characters"
    return f"Prefix is already set to {prefix}"
