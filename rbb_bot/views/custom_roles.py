from discord import Embed

from rbb_bot.application.custom_roles.contracts import (
    ColourPlacement,
    CustomRoleRefused,
    Refusal,
)
from rbb_bot.utils.views import ListView

REFUSAL_MESSAGES = {
    Refusal.DISABLED: "Custom roles are not enabled for this server",
    Refusal.NAME_TOO_LONG: "Role name is too long. It must be 100 characters or less.",
    Refusal.NAME_IN_USE: "Role name is already in use",
    Refusal.NOT_OWNED: "You can only remove bot-created roles recorded as yours",
    Refusal.SHARED: "This role is shared or managed and cannot be deleted automatically",
    Refusal.INVALID_MAX: "Max roles must be between 1 and 5",
}


def refusal_reply(refusal: CustomRoleRefused, prefix: str) -> dict:
    """Keyword arguments for `ctx.send` explaining why a request was turned down."""
    if refusal.refusal is Refusal.LIMIT_REACHED:
        return {
            "content": f"You already have {refusal.max_roles} custom roles. Remove one or ask a server administrator for help."
        }
    if refusal.refusal is Refusal.INVALID_COLOR:
        embed = Embed(
            title="Color must be a hex code or a valid color name",
            description="You can use google's color picker to get a hex code. "
            f"Alternatively you can use the `{prefix}roles colors` to "
            "see a list of valid color names",
        )
        embed.add_field(
            name="Hex color picker",
            value="https://www.google.com/search?q=color+picker",
        )
        return {"embed": embed}
    return {"content": REFUSAL_MESSAGES[refusal.refusal]}


def placement_reply(placement: ColourPlacement) -> str | None:
    """What the member must hear when their new role's colour may not show, if anything."""
    if placement.blocked_by is not None:
        return (
            f"Its colour won't show yet: your role <@&{placement.blocked_by}> is coloured "
            "and sits at or above my highest role. Once an admin moves my role above it, "
            "new custom roles will show their colour."
        )
    if placement.forbidden:
        return (
            "I couldn't position the role because I'm missing the `manage roles` "
            "permission, so its colour may not show."
        )
    return None


class ColorsList(ListView):
    def create_embed(self, colors: list[tuple[str, str]]) -> Embed:
        embed = Embed(title=f"Page {self.current_page + 1} of {len(self.view_chunks)}")
        for color in colors:
            name, hex_code = color
            embed.add_field(name=name, value=hex_code, inline=True)
        embed.set_footer(text=f"Source: https://htmlcolorcodes.com/color-names/")
        return embed
