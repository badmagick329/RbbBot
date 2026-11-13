from rbb_bot.utils.helpers import emoji_regex


class DiscordEmoteImages:
    """Prove a submitted emote is real by fetching its image from Discord's CDN.

    Any custom emote works, not only the guild's own, so the emote's markup is the only
    lead; the CDN answering 200 is the proof.
    """

    def __init__(self, web_client):
        self.web_client = web_client

    async def url(self, emote: str) -> str | None:
        match = emoji_regex.search(emote)
        if not match:
            return None
        params = "?animated=true" if match.group(1) == "a" else ""
        url = f"https://cdn.discordapp.com/emojis/{match.group(3)}.webp{params}"
        async with self.web_client.get(url) as response:
            if response.status == 200:
                return url
        return None
