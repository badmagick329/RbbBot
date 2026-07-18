from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from rbb_bot.cogs.privacy_cog import PrivacyCog, PrivacyDeleteView


@pytest.mark.asyncio
async def test_privacy_export_is_an_ephemeral_json_attachment():
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock())
    )
    cog = PrivacyCog(SimpleNamespace(logger=Mock()))

    with patch(
        "rbb_bot.cogs.privacy_cog.UserDataService.export",
        new=AsyncMock(
            return_value={"discord_user": None, "reminders": [], "source_entries": []}
        ),
    ):
        await PrivacyCog.export.callback(cog, interaction)

    kwargs = interaction.response.send_message.await_args.kwargs
    assert interaction.response.send_message.await_args.args == (
        "Here is your stored data.",
    )
    assert kwargs["ephemeral"] is True
    assert kwargs["file"].filename == "rbb-user-data.json"


@pytest.mark.asyncio
async def test_privacy_tags_updates_the_cached_global_preference():
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock())
    )
    cog = PrivacyCog(SimpleNamespace(logger=Mock()))

    with patch(
        "rbb_bot.cogs.privacy_cog.UserDataService.set_tag_opt_out",
        new=AsyncMock(return_value=True),
    ) as set_tag_opt_out:
        await PrivacyCog.tags.callback(cog, interaction, False)

    set_tag_opt_out.assert_awaited_once_with(1, True)
    interaction.response.send_message.assert_awaited_once_with(
        "Automatic tag responses are now disabled for you.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_privacy_delete_confirmation_is_requester_bound_and_pending_on_failure():
    cog = PrivacyCog(SimpleNamespace(logger=Mock()))
    view = PrivacyDeleteView(cog, user_id=1)
    other = SimpleNamespace(
        user=SimpleNamespace(id=2), response=SimpleNamespace(send_message=AsyncMock())
    )
    assert await view.interaction_check(other) is False
    other.response.send_message.assert_awaited_once()

    interaction = SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    with patch(
        "rbb_bot.cogs.privacy_cog.UserDataService.source_entries_for_deletion",
        new=AsyncMock(return_value=[SimpleNamespace()]),
    ), patch.object(
        cog.source_confirmation_service,
        "delete_confirmation_messages",
        new=AsyncMock(return_value=False),
    ):
        await view.children[0].callback(interaction)

    interaction.edit_original_response.assert_awaited_once()
    assert (
        "Deletion is pending"
        in interaction.edit_original_response.await_args.kwargs["content"]
    )
