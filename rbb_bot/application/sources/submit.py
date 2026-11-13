from datetime import date
from typing import Awaitable, Callable

from rbb_bot.application.sources.contracts import (
    ConfirmationPosts,
    EmoteImages,
    OperationalLogger,
    ReactionsRejected,
    Refusal,
    SourceDetails,
    SourceRefused,
    SourceRepository,
    SourceRequest,
    SourceSubmission,
)
from rbb_bot.domain.sources import MAX_FIELD_LENGTH, is_source_url, parse_source_date

Confirm = Callable[[SourceDetails], Awaitable[bool]]


class SubmitSource:
    """Record a source submission and post it to the confirmation channel for moderation.

    An edit does not change earlier submissions: it records another one for the same emote,
    and `source find` lets the newer fields win. So an edit needs no earlier submission and
    no source URL, only at least one field.

    The submitter is registered before anything is checked, so even a refused request
    leaves their user record and cached username behind, as it always has.
    """

    def __init__(
        self,
        repository: SourceRepository,
        emote_images: EmoteImages,
        posts: ConfirmationPosts,
        logger: OperationalLogger,
        today: Callable[[], date] = date.today,
    ):
        self.repository = repository
        self.emote_images = emote_images
        self.posts = posts
        self.logger = logger
        self.today = today

    async def add(self, request: SourceRequest, confirm: Confirm) -> bool:
        """Return False when the submitter declines `confirm`; raise `SourceRefused`."""
        return await self._submit(request, confirm, edit=False)

    async def edit(self, request: SourceRequest, confirm: Confirm) -> bool:
        """Return False when the submitter declines `confirm`; raise `SourceRefused`."""
        return await self._submit(request, confirm, edit=True)

    async def _submit(self, request, confirm, edit):
        submitter = await self.repository.register_submitter(
            request.submitter_id, request.submitter_name
        )
        if submitter.blacklisted:
            raise SourceRefused(Refusal.BLACKLISTED)
        if not edit and await self.repository.exists(request.emote):
            raise SourceRefused(Refusal.ALREADY_EXISTS)

        details = self._details(request, edit)
        emote_url = await self.emote_images.url(request.emote)
        if not emote_url:
            raise SourceRefused(Refusal.UNVERIFIED_EMOTE)
        if not await confirm(details):
            return False

        submission = SourceSubmission(
            emote=request.emote,
            emote_url=emote_url,
            details=details,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
            message_id=request.message_id,
            jump_url=request.jump_url,
            submitter=submitter,
        )
        await self._publish(submission)
        return True

    def _details(self, request, edit) -> SourceDetails:
        source_url = request.source_url
        event = request.event.strip() if request.event else request.event
        if source_url and len(source_url) > MAX_FIELD_LENGTH:
            raise SourceRefused(Refusal.URL_TOO_LONG)
        if event and len(event) > MAX_FIELD_LENGTH:
            raise SourceRefused(Refusal.EVENT_TOO_LONG)
        if not edit and not source_url:
            raise SourceRefused(Refusal.MISSING_URL)
        if source_url and not is_source_url(source_url):
            raise SourceRefused(Refusal.INVALID_URL)

        source_date = None
        if request.source_date:
            source_date = parse_source_date(request.source_date, self.today())
            if source_date is None:
                raise SourceRefused(Refusal.INVALID_DATE)
        if edit and not any([source_url, source_date, event]):
            raise SourceRefused(Refusal.NOTHING_TO_EDIT)
        return SourceDetails(source_url, event, source_date)

    async def _publish(self, submission):
        # The record stores the post's ID, so the post comes first; a post whose record
        # failed is withdrawn, since moderating it could reach no submission.
        post = await self.posts.publish(submission)
        try:
            await self.repository.record(submission, post)
        except Exception:
            await self.posts.retract(post.id)
            raise
        try:
            await self.posts.open_for_moderation(post.id)
        except ReactionsRejected:
            self.logger.exception(
                "Source saved but moderation reactions could not be added"
            )
