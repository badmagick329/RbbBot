import asyncio
from datetime import datetime, timezone


class ReminderWorker:
    """Use persisted reminders as the queue so deletion and restarts need no scheduler sync.

    One bot process owns delivery. Failed sends remain pending for the next poll.
    Discord sends and database deletion cannot form an atomic transaction.
    """

    def __init__(self, repository, deliver, bot, interval=30):
        self.repository = repository
        self.deliver = deliver
        self.bot = bot
        self.interval = interval
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.run(), name="reminder-delivery")

    async def close(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)

    async def run_once(self):
        now = datetime.now(timezone.utc)
        for reminder_id in await self.repository.due_ids(now):
            try:
                await self.deliver.execute(reminder_id, now)
            except Exception:
                self.bot.logger.exception(
                    "Reminder %s delivery failed; retained for retry", reminder_id
                )

    async def run(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                await self.run_once()
            except Exception:
                self.bot.logger.exception(
                    "Could not load due reminders; retrying next poll"
                )
            await asyncio.sleep(self.interval)
