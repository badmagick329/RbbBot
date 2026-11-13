from discord import Embed

from rbb_bot.application.sources.contracts import (
    Refusal,
    SourceDetails,
    SourceRefused,
    SourceSubmission,
)
from rbb_bot.application.sources.lookup import SourceLookup
from rbb_bot.domain.sources import MAX_FIELD_LENGTH
from rbb_bot.utils.views import ListView

REFUSAL_MESSAGES = {
    Refusal.BLACKLISTED: "You are blacklisted from adding sources",
    Refusal.URL_TOO_LONG: f"Source URL is too long. Max {MAX_FIELD_LENGTH} characters",
    Refusal.EVENT_TOO_LONG: f"Event is too long. Max {MAX_FIELD_LENGTH} characters",
    Refusal.MISSING_URL: "Please provide a source URL",
    Refusal.INVALID_URL: "Please provide a valid source URL",
    Refusal.NOTHING_TO_EDIT: "At least one of these is required: source_url, source_date, event",
    Refusal.UNVERIFIED_EMOTE: "Could not validate the emote url",
}

SUBMITTER_ID_LABEL = "User ID"


def refusal_reply(refusal: SourceRefused, prefix: str, source_date: str | None) -> str:
    if refusal.refusal is Refusal.ALREADY_EXISTS:
        return (
            "An entry for this emote already exists. "
            f"Use {prefix}source edit to edit or add more information"
        )
    if refusal.refusal is Refusal.INVALID_DATE:
        return (
            f"`{source_date}` is not a valid date. Date format is YYMMDD. "
            "Future dates are not permitted"
        )
    return REFUSAL_MESSAGES[refusal.refusal]


def confirmation_prompt(details: SourceDetails, edit: bool) -> str:
    prompt = ""
    if details.source_url:
        prompt = f"Source: {details.source_url}\n"
    if details.source_date:
        prompt += f"Date: {details.source_date}\n"
    if details.event:
        prompt += f"Event: {details.event}\n"
    return prompt + ("Edit these fields?" if edit else "Is this correct?")


def source_found(lookup: SourceLookup) -> str:
    message = ""
    if lookup.source_date:
        message = f"{lookup.source_date} "
    if lookup.event:
        message += f"{lookup.event}\n"
    if lookup.source_url:
        message += f"{lookup.source_url}\n"
    return message + f"Submitted by {', '.join(lookup.submitter_names)}"


def confirmation_post(submission: SourceSubmission) -> str:
    """The text moderators read; `submitter_id` reads the submitter back out of it."""
    emote = submission.emote
    details = submission.details
    fields = {
        "Emote": f"`{emote[0]} {emote[1:]}`",
        "Emote url": submission.emote_url,
        "Jump url": submission.jump_url,
        "Source link": details.source_url,
        "Event": details.event,
        "Date": details.source_date,
        SUBMITTER_ID_LABEL: submission.submitter.id,
        "Message ID": submission.message_id,
        "User name": submission.submitter.cached_username,
    }
    # User-supplied fields must not introduce moderation metadata lines.
    return "\n".join(
        f"{key}: {' '.join(str(value).splitlines())}" for key, value in fields.items()
    )


def submitter_id(content: str) -> int | None:
    """The submitter a confirmation post names, if it names exactly one.

    Posts made before user fields were flattened can carry a forged ID line in their
    event, so more than one ID line makes the post name nobody.
    """
    values = []
    for line in content.splitlines():
        label, separator, value = line.partition(":")
        if separator and label.lower() == SUBMITTER_ID_LABEL.lower():
            values.append(value.strip())
    if len(values) != 1 or not values[0].isdecimal():
        return None
    return int(values[0])


class SubmissionsView(ListView):
    def create_embed(self, submissions: list[tuple[str, int]]) -> Embed:
        page_header = ""
        if len(self.view_chunks) > 1:
            page_header = f"\nPage {self.current_page + 1} of {len(self.view_chunks)}"
        header = f"Source submissions by users{page_header}"

        embed = Embed(title=header)
        for user, count in submissions:
            embed.add_field(name=user, value=f"{count} submissions", inline=False)
        return embed
