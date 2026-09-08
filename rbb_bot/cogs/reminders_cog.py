from datetime import datetime, timezone
from typing import Optional

from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Cog, Context
from rbb_bot.application.reminders.use_cases import (
    DEFAULT_TEXT,
    MAX_TEXT,
    CreateReminderRequest,
    CreateReminder,
    GetReminder,
    CancelReminder,
    DeliverReminder,
)
from rbb_bot.infrastructure.reminders.repository import TortoiseReminderRepository
from rbb_bot.infrastructure.reminders.discord_delivery import DiscordReminderDelivery
from rbb_bot.infrastructure.reminders.worker import ReminderWorker
from rbb_bot.infrastructure.reminders.time_parser import parse_reminder_time
from rbb_bot.views.reminders import RemindersList, detailed_time, reminder_summary

from rbb_bot.utils.helpers import truncate


class RemindersCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.time_examples = (
            "`saturday at 5pm` - Coming saturday at 5pm UTC\n"
            "`8pm +1UTC` - 8pm UTC + 1 hour (British Summer Time)\n"
            "`in 2 mins` - In 2 minutes\n"
            "`tomorrow at 6pm KST` - Tomorrow at 6pm Korean Standard Time\n"
            "`2022 10 31 14:00 PT` - 2022-10-31 14:00 Pacific Time\n"
            "Other date formats like `2022/10/31` or `31-10-2022` are also supported"
        )
        self.repository = TortoiseReminderRepository()
        self.create_reminder = CreateReminder(self.repository)
        self.get_reminder = GetReminder(self.repository)
        self.cancel_reminder = CancelReminder(self.repository)
        self.worker = ReminderWorker(
            self.repository,
            DeliverReminder(self.repository, DiscordReminderDelivery(bot)),
            bot,
        )

    async def cog_load(self) -> None:
        self.worker.start()

    async def cog_unload(self) -> None:
        await self.worker.close()

    @commands.hybrid_group(
        brief="Set and manage reminders",
        aliases=["reminder", "remindme"],
        invoke_without_command=True,
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def remind(self, ctx: Context, *args, **kwargs):
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.set_reminder, *args, **kwargs)

    @remind.command(brief="Enable reminder messages in this server")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def enable(self, ctx: Context, enabled: Optional[bool] = True):
        await self.repository.set_channel_enabled(ctx.guild.id, enabled)
        await ctx.send(
            f"Reminders {'enabled' if enabled else 'disabled'} for {ctx.guild}"
        )

    @remind.command(name="set", brief="Set a reminder")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def set_reminder(
        self,
        ctx: Context,
        time: str,
        channel: Optional[TextChannel] = None,
        text: Optional[str] = None,
    ):
        """
        Set a reminder

        Parameters
        ----------
        time: str
            The time to set the reminder for (Required)
        channel: Optional[TextChannel]
            The channel to send the reminder in. Does not work in DMs (Optional)
        text: str
            The text to include in the reminder (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        get_confirmation = True
        if text and len(text) > MAX_TEXT:
            return await ctx.send(
                f"Reminder text must be at most {MAX_TEXT} characters"
            )

        if ctx.guild:
            if channel and not await self.repository.channel_enabled(ctx.guild.id):
                prompt = f"Reminders are not enabled in {ctx.guild}. Would you like to be DM'd instead?"
                if not (await self.bot.get_confirmation(ctx, prompt)):
                    return
                channel = None
                get_confirmation = False

        try:
            due_time = parse_reminder_time(time, datetime.now(timezone.utc))
        except ValueError:
            return await ctx.send(
                f"Please specify a valid time. Examples:\n{self.time_examples}"
            )

        due_time_str = detailed_time(due_time)

        if get_confirmation:
            if due_time < datetime.now(timezone.utc):
                return await ctx.send("I can't remind you in the past :(")

            prompt = f"Set a reminder for {due_time_str}"

            if channel:
                prompt = f"{prompt} in {channel.mention}"
            if text:
                prompt = f"{prompt} to `{truncate(text,300)}`?"
            else:
                prompt = f"{prompt}?"

            if not (await self.bot.get_confirmation(ctx, prompt)):
                return

        if due_time < datetime.now(timezone.utc):
            return await ctx.send("Due time has passed now :(")

        try:
            await self.create_reminder.execute(
                CreateReminderRequest(
                    user_id=ctx.author.id,
                    due_time=due_time,
                    guild_id=ctx.guild.id if ctx.guild else None,
                    channel_id=channel.id if channel else None,
                    text=text or DEFAULT_TEXT,
                ),
                datetime.now(timezone.utc),
            )
        except ValueError as error:
            await ctx.send(str(error))
            return

        await ctx.send(
            f"Reminder set{' for ' + due_time_str if not get_confirmation else ''}. "
            f"Check your reminders with `{ctx.prefix}remind list`."
        )

    @remind.command(brief="List your reminders")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def list(self, ctx: Context):
        """
        List your reminders
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        reminders = await self.repository.list_for_user(ctx.author.id)
        if not reminders:
            await ctx.send("You don't have any reminders set.")
            return

        view = RemindersList(ctx, reminders, 5)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)

    @remind.command(brief="Show reminder text")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def show(self, ctx: Context, reminder_id: int):
        """
        Show the text of a reminder
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        reminder = await self.get_reminder.execute(reminder_id, ctx.author.id)
        if not reminder:
            await ctx.send("Reminder not found")
            return

        await ctx.send(f"Reminder text:\n{reminder.text}")

    @remind.command(brief="Remove a reminder by ID")
    async def remove(self, ctx: Context, reminder_id: int):
        """
        Remove a reminder by ID

        Parameters
        ----------
        reminder_id: int
            The ID of the reminder to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        reminder = await self.get_reminder.execute(reminder_id, ctx.author.id)
        if not reminder:
            await ctx.send(
                "I couldn't find a reminder with that ID. Check your reminders with "
                f"`{ctx.prefix}remind list`. The ID is the number between []"
            )
            return

        if not (
            await self.bot.get_confirmation(
                ctx, f"Remove reminder\n{reminder_summary(reminder)}?"
            )
        ):
            return
        deleted = await self.cancel_reminder.execute(reminder_id, ctx.author.id)
        await ctx.send("Reminder deleted" if deleted else "Reminder no longer pending")


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
