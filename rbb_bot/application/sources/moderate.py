from rbb_bot.application.sources.contracts import (
    ConfirmationPost,
    OperationalLogger,
    SourceRepository,
)


class ModerateSubmission:
    """Act on the owner's reaction to one confirmation post.

    The blacklist reads the submitter from the post's text rather than from the stored
    submission, because the hammer deletes the submission and removing the hammer must
    still find whom to lift the blacklist from. Posts by anyone but the bot are ignored, so
    nobody can name a submitter by writing a look-alike post in the confirmation channel.
    """

    def __init__(
        self,
        repository: SourceRepository,
        post: ConfirmationPost,
        logger: OperationalLogger,
    ):
        self.repository = repository
        self.post = post
        self.logger = logger

    async def remove(self) -> None:
        if not await self.post.from_bot():
            return
        await self.repository.forget(self.post.id)
        await self.post.mark_deleted()

    async def blacklist_submitter(self) -> None:
        user_id = await self._submitter_id()
        if user_id is None:
            return
        blacklisted = await self.repository.blacklisted(user_id)
        if blacklisted is None:
            return
        if blacklisted:
            self.logger.info("User already blacklisted from adding sources")
            return
        await self.repository.blacklist(user_id)
        self.logger.info("User blacklisted from adding sources user_id=%s", user_id)

    async def lift_blacklist(self) -> None:
        user_id = await self._submitter_id()
        if user_id is None:
            return
        if await self.repository.lift_blacklist(user_id):
            self.logger.info(
                "User no longer blacklisted from adding sources user_id=%s", user_id
            )

    async def _submitter_id(self) -> int | None:
        if not await self.post.from_bot():
            return None
        return await self.post.submitter_id()
