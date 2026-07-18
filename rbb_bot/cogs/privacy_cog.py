"""Slash-only self-service privacy controls."""

import io
import json

import discord
from discord import app_commands
from discord.ext import commands

from rbb_bot.services.source_confirmation_service import SourceConfirmationService
from rbb_bot.services.user_data_service import UserDataService


class PrivacyDeleteView(discord.ui.View):
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "This deletion confirmation belongs to another user.", ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Delete my data", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        source_entries = await UserDataService.source_entries_for_deletion(self.user_id)
        deleted_messages = (
            await self.cog.source_confirmation_service.delete_confirmation_messages(
                source_entries, scope="user", scope_id=self.user_id
            )
        )
        if not deleted_messages:
            await interaction.edit_original_response(
                content=(
                    "Deletion is pending because I could not remove every source "
                    "confirmation message. Please try again after access is restored."
                ),
                view=None,
            )
            return

        deleted = await UserDataService.delete_user_data(self.user_id)
        message = (
            "Your stored data has been deleted." if deleted else "No stored data found."
        )
        await interaction.edit_original_response(content=message, view=None)


class PrivacyCog(
    commands.GroupCog,
    group_name="privacy",
    group_description="Export, delete, or control your stored data.",
):
    def __init__(self, bot):
        self.bot = bot
        self.source_confirmation_service = SourceConfirmationService(bot)

    async def cog_load(self):
        await UserDataService.load_tag_opt_out_cache()
        self.bot.logger.debug("PrivacyCog loaded!")

    @app_commands.command(
        name="export", description="Download the data stored for you."
    )
    async def export(self, interaction: discord.Interaction):
        data = await UserDataService.export(interaction.user.id)
        payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        await interaction.response.send_message(
            "Here is your stored data.",
            file=discord.File(io.BytesIO(payload), filename="rbb-user-data.json"),
            ephemeral=True,
        )

    @app_commands.command(
        name="tags", description="Show or change automatic tag-response processing."
    )
    @app_commands.describe(enabled="Enable automatic tag responses for your account.")
    async def tags(self, interaction: discord.Interaction, enabled: bool | None = None):
        if enabled is None:
            opted_out = UserDataService.is_tag_opted_out(interaction.user.id)
            await interaction.response.send_message(
                f"Automatic tag responses are {'disabled' if opted_out else 'enabled'} for you.",
                ephemeral=True,
            )
            return

        await UserDataService.set_tag_opt_out(interaction.user.id, not enabled)
        await interaction.response.send_message(
            f"Automatic tag responses are now {'enabled' if enabled else 'disabled'} for you.",
            ephemeral=True,
        )

    @app_commands.command(
        name="delete", description="Permanently delete your stored data."
    )
    async def delete(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "This permanently deletes your reminders, source submissions, source "
            "confirmation messages, blacklist state, cached username, and tag preference.",
            view=PrivacyDeleteView(self, interaction.user.id),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(PrivacyCog(bot))
