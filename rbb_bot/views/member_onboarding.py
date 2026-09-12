from discord import Embed, Member

from rbb_bot.domain.member_onboarding import GreetingTemplate
from rbb_bot.utils.views import ListView
from rbb_bot.utils.helpers import truncate


def create_greeting_embed(greeting: GreetingTemplate, member: Member) -> Embed:
    # Template placeholders can expand beyond the configured text's original size.
    title = greeting.title.replace("{username}", member.name)[:256]
    description = greeting.description.replace("{mention}", member.mention)[:4096]
    embed = Embed(title=title, description=description)
    embed.set_thumbnail(url=member.display_avatar)
    if greeting.show_member_count:
        embed.set_footer(text=f"Member #{member.guild.member_count}")
    return embed


class MessagesList(ListView):
    def create_embed(self, messages) -> Embed:
        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)} - {len(self.list_items)} messages"
        )
        for message in messages:
            embed.add_field(
                name=f"[{message.id}]",
                value=truncate(message.content, 200),
                inline=False,
            )
        return embed


def role_embed(roles) -> Embed:
    embed = Embed(title="Auto Roles")
    for role in roles:
        status = "" if role.assignable else " (currently unassignable)"
        embed.add_field(
            name=f"{role.name} [{role.id}]",
            value=f"<@&{role.id}>{status}",
            inline=False,
        )
    return embed


def assignment_summary(result) -> str:
    text = f"Auto roles applied to {result.applied_members} members; {len(result.failures)} failed."
    if result.skipped_role_ids:
        text += f" Skipped {len(result.skipped_role_ids)} unassignable roles. Check permissions and role hierarchy."
    return text
