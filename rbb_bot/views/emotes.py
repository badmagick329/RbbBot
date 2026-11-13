from rbb_bot.application.emotes.contracts import EmoteChannelRefused, Refusal
from rbb_bot.domain.emotes import MAX_CHANNEL_MESSAGE

REFUSAL_MESSAGES = {
    Refusal.ALREADY_ASSIGNED: "This channel is already assigned as the emotes channel",
    Refusal.MESSAGE_TOO_LONG: f"Message is too long. Max length is {MAX_CHANNEL_MESSAGE}",
    Refusal.NO_CHANNEL: "No channel assigned to post emotes in",
    Refusal.MISSING_MANAGE_MESSAGES: "I don't have manage messages permission in the emotes channel",
    Refusal.MISSING_READ_HISTORY: "I don't have read message history permission in the emotes channel",
}


def refusal_reply(refusal: EmoteChannelRefused) -> str:
    return REFUSAL_MESSAGES[refusal.refusal]
