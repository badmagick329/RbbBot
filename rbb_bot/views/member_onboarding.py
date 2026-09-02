from discord import Embed, Member

from rbb_bot.domain.member_onboarding import GreetingTemplate


def create_greeting_embed(greeting: GreetingTemplate, member: Member) -> Embed:
    title = greeting.title.replace("{username}", member.name)
    description = greeting.description.replace("{mention}", member.mention)
    embed = Embed(title=title, description=description)
    embed.set_thumbnail(url=member.display_avatar)
    if greeting.show_member_count:
        embed.set_footer(text=f"Member #{member.guild.member_count}")
    return embed
