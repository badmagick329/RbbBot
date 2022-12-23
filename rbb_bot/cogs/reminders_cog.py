import asyncio
from datetime import datetime, timezone
from typing import Optional

import dateparser
import discord
from aioscheduler import TimedScheduler
from discord import TextChannel
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.utils import format_dt
from models import DiscordUser, Guild, Reminder

from rbb_bot.utils.helpers import truncate
from rbb_bot.utils.views import ListView


class RemindersList(ListView):
    def create_embed(self, reminders: list[Reminder]) -> discord.Embed:
        assert reminders, "No reminders to create embed from"

        user = reminders[0].discord_user.user
        embed = discord.Embed(
            title=f"{user}'s reminders", color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=user.avatar.url)

        for reminder in reminders:
            embed.add_field(
                name=f"[{reminder.id}] {truncate(reminder.text, 50)}",
                value=f"Created at {format_dt(reminder.created_at, style='f')}",
                inline=False,
            )

            channel = (
                f"Sending in {reminder.channel.mention}" if reminder.channel else ""
            )

            embed.add_field(
                name="Due",
                value=f"{reminder.detailed_format()} {channel}",
            )
        return embed


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
        self.scheduler = None

    async def cog_load(self) -> None:
        self.scheduler = TimedScheduler(prefer_utc=True)
        self.scheduler.start()
        load_task = asyncio.create_task(self.load_reminders())
        load_task.add_done_callback(self.load_error)
        self.bot.logger.debug("RemindersCog Cog loaded!")

    async def cog_unload(self) -> None:
        self.scheduler._task.cancel()
        self.bot.logger.debug("RemindersCog Cog unloaded!")

    def load_error(self, task: asyncio.Task):
        exc = task.exception()
        if exc:
            self.bot.logger.error(
                f"Error loading reminders: {exc}", exc_info=exc, stack_info=True
            )

    async def load_reminders(self):
        self.bot.logger.debug("Waiting for bot to be ready")
        await self.bot.wait_until_ready()
        self.bot.logger.debug(f"Scheduling reminders")
        try:
            reminders = await Reminder.all()
            for reminder in reminders:
                if reminder.is_due:
                    await self.send_reminder(reminder.id, late=True)
                    continue

                self.scheduler.schedule(
                    self.send_reminder(reminder.id),
                    reminder.due_time.replace(tzinfo=None),
                )
        except Exception as e:
            self.bot.logger.error(
                f"Error scheduling reminders: {e}", exc_info=e, stack_info=True
            )

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
    async def enable(self, ctx: Context, enabled: Optional[bool] = True):
        await Guild.update_or_create(
            id=ctx.guild.id, defaults={"reminders_enabled": enabled}
        )
        await ctx.send(
            f"Reminders {'enabled' if enabled else 'disabled'} for {ctx.guild}"
        )

    @remind.command(name="set", brief="Set a reminder")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def set_reminder(
        self,
        ctx: Context,
        time: str,
        channel: Optional[TextChannel],
        *,
        text: Optional[str],
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
        guild = None
        if text and len(text) > Reminder.MAX_TEXT:
            return await ctx.send(
                f"Reminder text must be less than {Reminder.MAX_TEXT} characters"
            )

        if ctx.guild:
            guild, _ = await Guild.get_or_create(id=ctx.guild.id)
            if channel and not guild.reminders_enabled:
                prompt = f"Reminder are not enabled in {ctx.guild}. Would you like to be DM'd instead?"
                if not (await self.bot.get_confirmation(ctx, prompt)):
                    return
                channel = None
                get_confirmation = False

        settings = {
            "PREFER_DATES_FROM": "future",
        }
        parsed_date = dateparser.parse(time, settings=settings)
        parsed_date: datetime
        if not parsed_date:
            return await ctx.send(
                f"Please specify a valid time. Examples:\n{self.time_examples}"
            )

        due_time = parsed_date.astimezone(timezone.utc)
        due_time_str = (
            f"{format_dt(due_time, style='f')} ({format_dt(due_time, style='R')})"
        )

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

        user, _ = await DiscordUser.get_or_create(id=ctx.author.id)

        reminder = await Reminder.create(
            discord_user=user,
            due_time=due_time,
            channel_id=channel.id if channel else None,
            guild=guild,
            text=truncate(text, Reminder.MAX_TEXT) if text else Reminder.DEFAULT_TEXT,
        )

        await ctx.send(
            f"Reminder set{' for ' + due_time_str if not get_confirmation else ''}. "
            f"Check your reminders with `{ctx.prefix}remind list`."
        )

        self.scheduler.schedule(
            self.send_reminder(reminder.id),
            due_time.replace(tzinfo=None),
        )

    @remind.command(brief="List your reminders")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def list(self, ctx: Context):
        """
        List your reminders
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        reminders = (
            await Reminder.filter(discord_user__id=ctx.author.id)
            .all()
            .prefetch_related("discord_user", "guild")
        )
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

        reminder = await Reminder.filter(
            id=reminder_id, discord_user__id=ctx.author.id
        ).first()
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

        reminder = await Reminder.filter(
            id=reminder_id, discord_user__id=ctx.author.id
        ).first()
        if not reminder:
            await ctx.send(
                "I couldn't find a reminder with that ID. Check your reminders with "
                f"`{ctx.prefix}remind list`. The ID is the number between []"
            )
            return

        if not (
            await self.bot.get_confirmation(ctx, f"Remove reminder\n{str(reminder)}?")
        ):
            return
        await reminder.delete()
        await ctx.send("Reminder deleted")

    async def send_reminder(self, reminder_id: int, late=False):
        reminder = (
            await Reminder.filter(id=reminder_id)
            .first()
            .prefetch_related("discord_user", "guild")
        )
        user = reminder.discord_user.user
        message_content = "Sorry for the late reminder. " if late else ""
        send_to = user
        channel = reminder.channel

        if reminder.channel and not reminder.guild.reminders_enabled:
            message_content = (
                f"{message_content}"
                f"Could not send reminder in {reminder.channel}. "
                f"The server has disabled reminders"
            )
        elif reminder.channel_id and not channel:
            message_content = (
                f"Could not send reminder in set channel. It may have been deleted"
            )
        elif reminder.channel:
            try:
                send_to = reminder.channel
            except Exception as e:
                if isinstance(e, discord.Forbidden):
                    message_content = (
                        f"{message_content}"
                        f"Could not send reminder in {reminder.channel}. "
                        f"Reminders may have been disabled in the server"
                    )
                else:
                    await self.bot.send_error(
                        exc=e, comment=f"Channel not found\n{reminder=}"
                    )
                    message_content = f"Failed to send reminder to set channel"

        message_content = (
            f"{message_content}{reminder.reminder_text}"
            if message_content
            else reminder.reminder_text
        )
        await send_to.send(message_content)

        await reminder.delete()


async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
