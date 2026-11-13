from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.sources.contracts import (
    PublishedPost,
    ReactionsRejected,
    RecordedSource,
    Refusal,
    SourceDetails,
    SourceRefused,
    SourceRequest,
    SourceSubmission,
    Submitter,
    SubmitterTally,
)
from rbb_bot.application.sources.lookup import CountSubmissions, FindSource
from rbb_bot.application.sources.moderate import ModerateSubmission
from rbb_bot.application.sources.submit import SubmitSource
from rbb_bot.infrastructure.sources.confirmation import (
    DiscordConfirmationPost,
    DiscordConfirmationPosts,
)
from rbb_bot.settings.const import BotEmojis
from rbb_bot.views.sources import (
    confirmation_post,
    confirmation_prompt,
    source_found,
    submitter_id,
)

pytestmark = pytest.mark.asyncio

EMOTE = "<:wave:123>"
EMOTE_URL = "https://cdn.discordapp.com/emojis/123.webp"
TODAY = date(2026, 11, 13)
POST = PublishedPost(900, "https://discord.com/channels/1/2/900")


class FakeRepository:
    """In-memory submissions and users; `users` maps ID to [cached name, blacklist]."""

    def __init__(self, users=None, records=None, record_failure=None):
        self.users = users if users is not None else {}
        self.records = records if records is not None else []
        self.record_failure = record_failure
        self.lookups = []

    async def register_submitter(self, user_id, username):
        user = self.users.setdefault(user_id, [username, None])
        if not user[0]:
            user[0] = username
        return Submitter(user_id, user[0], (user[1] or {}).get("source") == "blacklist")

    async def exists(self, emote):
        return any(submission.emote == emote for submission, _ in self.records)

    async def record(self, submission, post):
        if self.record_failure is not None:
            raise self.record_failure
        self.records.append((submission, post))

    async def sources(self, emote):
        return tuple(
            RecordedSource(s.details, s.submitter.id, s.submitter.cached_username)
            for s, post in sorted(self.records, key=lambda r: r[1].id)
            if s.emote == emote
        )

    async def tallies(self):
        counts = {}
        for submission, _ in self.records:
            counts[submission.submitter.id] = counts.get(submission.submitter.id, 0) + 1
        return tuple(
            SubmitterTally(user_id, self.users[user_id][0], count)
            for user_id, count in counts.items()
        )

    async def forget(self, post_id):
        self.records = [r for r in self.records if r[1].id != post_id]

    async def blacklisted(self, user_id):
        self.lookups.append(user_id)
        if user_id not in self.users:
            return None
        return (self.users[user_id][1] or {}).get("source") == "blacklist"

    async def blacklist(self, user_id):
        self.users[user_id][1] = {
            **(self.users[user_id][1] or {}),
            "source": "blacklist",
        }

    async def lift_blacklist(self, user_id):
        self.lookups.append(user_id)
        blacklist = (self.users.get(user_id) or [None, None])[1] or {}
        if "source" not in blacklist:
            return False
        self.users[user_id][1] = {k: v for k, v in blacklist.items() if k != "source"}
        return True


class FakeEmoteImages:
    def __init__(self, url=EMOTE_URL):
        self.found = url

    async def url(self, emote):
        return self.found


class FakePosts:
    def __init__(self, reactions_failure=None):
        self.reactions_failure = reactions_failure
        self.events = []

    async def publish(self, submission):
        # Each post gets a later ID, as Discord's snowflakes do.
        published = sum(1 for event in self.events if event[0] == "publish")
        self.events.append(("publish", submission))
        return PublishedPost(POST.id + published, POST.jump_url)

    async def retract(self, post_id):
        self.events.append(("retract", post_id))

    async def open_for_moderation(self, post_id):
        if self.reactions_failure is not None:
            raise self.reactions_failure
        self.events.append(("react", post_id))


class FakePost:
    def __init__(self, content, from_bot=True, post_id=POST.id):
        self.id = post_id
        self.content = content
        self.bot_authored = from_bot
        self.marked = False

    async def from_bot(self):
        return self.bot_authored

    async def submitter_id(self):
        return submitter_id(self.content)

    async def mark_deleted(self):
        self.marked = True


def request(**changes):
    fields = dict(
        emote=EMOTE,
        source_url="https://example.com/clip",
        event=None,
        source_date=None,
        guild_id=1,
        channel_id=2,
        message_id=3,
        jump_url="https://discord.com/channels/1/2/3",
        submitter_id=12,
        submitter_name="fan",
    )
    fields.update(changes)
    return SourceRequest(**fields)


def submitter(user_id=12, name="fan"):
    return Submitter(user_id, name, False)


def submission(details, user=None, emote=EMOTE):
    return SourceSubmission(
        emote, EMOTE_URL, details, 1, 2, 3, "jump", user or submitter()
    )


def details(source_url=None, event=None, source_date=None):
    return SourceDetails(source_url, event, source_date)


def submit(repository, posts=None, images=None, logger=None):
    return SubmitSource(
        repository,
        images or FakeEmoteImages(),
        posts or FakePosts(),
        logger or Mock(),
        today=lambda: TODAY,
    )


def accepting(seen=None):
    async def confirm(details):
        if seen is not None:
            seen.append(details)
        return True

    return confirm


async def declining(details):
    return False


# Submitting


async def test_added_source_is_posted_then_recorded_with_its_post_and_opened_for_moderation():
    repository = FakeRepository()
    posts = FakePosts()
    seen = []

    added = await submit(repository, posts).add(
        request(event="  Music Bank  ", source_date="241231"), accepting(seen)
    )

    expected = details("https://example.com/clip", "Music Bank", date(2024, 12, 31))
    assert added is True
    assert seen == [expected]
    recorded, post = repository.records[0]
    assert post == POST
    assert recorded.details == expected
    assert recorded.emote_url == EMOTE_URL
    assert recorded.submitter == submitter()
    assert posts.events == [("publish", recorded), ("react", POST.id)]


async def test_declined_confirmation_posts_and_records_nothing():
    repository = FakeRepository()
    posts = FakePosts()

    assert await submit(repository, posts).add(request(), declining) is False

    assert repository.records == []
    assert posts.events == []


async def test_blacklisted_submitter_is_refused_but_still_registered():
    repository = FakeRepository(users={12: [None, {"source": "blacklist"}]})
    posts = FakePosts()

    with pytest.raises(SourceRefused) as refused:
        await submit(repository, posts).add(request(), accepting())

    assert refused.value.refusal is Refusal.BLACKLISTED
    assert repository.users[12][0] == "fan"
    assert posts.events == []


async def test_submitter_keeps_the_name_cached_at_their_first_submission():
    repository = FakeRepository(users={12: ["old-name", None]})

    await submit(repository).add(request(submitter_name="new-name"), accepting())

    assert repository.records[0][0].submitter.cached_username == "old-name"


async def test_adding_an_emote_that_has_a_source_is_refused_but_editing_adds_another():
    repository = FakeRepository()
    await submit(repository).add(request(), accepting())

    with pytest.raises(SourceRefused) as refused:
        await submit(repository).add(request(), accepting())
    assert refused.value.refusal is Refusal.ALREADY_EXISTS

    edited = await submit(repository).edit(
        request(source_url=None, event="Inkigayo"), accepting()
    )
    assert edited is True
    assert [s.details for s, _ in repository.records] == [
        details("https://example.com/clip"),
        details(None, "Inkigayo"),
    ]


async def test_editing_an_emote_without_any_source_is_accepted():
    repository = FakeRepository()

    assert await submit(repository).edit(
        request(source_url=None, source_date="240101"), accepting()
    )
    assert repository.records[0][0].details == details(source_date=date(2024, 1, 1))


@pytest.mark.parametrize(
    "edit,changes,refusal",
    [
        (False, {"source_url": "https://x.co/" + "a" * 243}, Refusal.URL_TOO_LONG),
        (False, {"event": " " + "e" * 256 + " "}, Refusal.EVENT_TOO_LONG),
        (False, {"source_url": None}, Refusal.MISSING_URL),
        (False, {"source_url": "example.com/clip"}, Refusal.INVALID_URL),
        (True, {"source_url": "https://nodot"}, Refusal.INVALID_URL),
        (False, {"source_date": "241301"}, Refusal.INVALID_DATE),
        (False, {"source_date": "261114"}, Refusal.INVALID_DATE),
        (True, {"source_url": None, "event": "   "}, Refusal.NOTHING_TO_EDIT),
    ],
)
async def test_invalid_requests_are_refused_before_anything_is_posted(
    edit, changes, refusal
):
    repository = FakeRepository()
    posts = FakePosts()
    use_case = submit(repository, posts)

    with pytest.raises(SourceRefused) as refused:
        await (use_case.edit if edit else use_case.add)(request(**changes), accepting())

    assert refused.value.refusal is refusal
    assert posts.events == []
    assert repository.records == []


async def test_limits_admit_fields_at_exactly_the_maximum_and_today_as_a_date():
    repository = FakeRepository()
    url = "https://x.co/" + "a" * 242

    await submit(repository).add(
        request(source_url=url, event="e" * 255, source_date="261113"), accepting()
    )

    assert repository.records[0][0].details == details(url, "e" * 255, TODAY)


async def test_emote_discord_cannot_serve_is_refused_before_confirmation():
    seen = []

    with pytest.raises(SourceRefused) as refused:
        await submit(FakeRepository(), images=FakeEmoteImages(None)).add(
            request(), accepting(seen)
        )

    assert refused.value.refusal is Refusal.UNVERIFIED_EMOTE
    assert seen == []


async def test_failed_recording_retracts_the_post_and_propagates():
    repository = FakeRepository(record_failure=RuntimeError("database failed"))
    posts = FakePosts()

    with pytest.raises(RuntimeError):
        await submit(repository, posts).add(request(), accepting())

    assert [event[0] for event in posts.events] == ["publish", "retract"]
    assert posts.events[1] == ("retract", POST.id)


async def test_rejected_reactions_keep_the_submission_and_are_logged():
    repository = FakeRepository()
    logger = Mock()
    posts = FakePosts(reactions_failure=ReactionsRejected(POST.id))

    assert await submit(repository, posts, logger=logger).add(request(), accepting())

    assert len(repository.records) == 1
    logger.exception.assert_called_once()


# Looking up


async def test_find_merges_newer_fields_over_older_and_credits_each_submitter_once():
    first, second = submitter(12, "fan"), submitter(13, "other")
    repository = FakeRepository(
        records=[
            (submission(details(None, "Edit", None), second), PublishedPost(3, "")),
            (
                submission(details("https://a.co/1", "Old", date(2024, 1, 1)), first),
                PublishedPost(1, ""),
            ),
            (submission(details("https://a.co/2"), first), PublishedPost(2, "")),
            (
                submission(details("https://b.co"), first, "<:x:1>"),
                PublishedPost(4, ""),
            ),
        ]
    )

    lookup = await FindSource(repository).execute(EMOTE)

    assert source_found(lookup) == (
        "2024-01-01 Edit\nhttps://a.co/2\nSubmitted by fan, other"
    )


async def test_find_returns_nothing_for_an_emote_without_submissions():
    assert await FindSource(FakeRepository()).execute(EMOTE) is None


async def test_counts_prefer_current_names_merge_equal_names_and_rank_by_count():
    users = {12: ["a", None], 13: ["b", None], 14: ["gone", None]}
    records = [
        (submission(details(), submitter(user_id)), PublishedPost(i, ""))
        for i, user_id in enumerate([12, 13, 13, 14, 14, 14])
    ]
    repository = FakeRepository(users=users, records=records)
    current = {12: "same", 13: "same"}

    counts = await CountSubmissions(repository, current.get).execute()

    assert counts == (("same", 3), ("gone", 3))


# Moderating


async def test_removal_forgets_the_posts_submission_and_marks_the_post():
    repository = FakeRepository(
        records=[
            (submission(details()), POST),
            (submission(details()), PublishedPost(1, "")),
        ]
    )
    post = FakePost("User ID: 12")

    await ModerateSubmission(repository, post, Mock()).remove()

    assert [p.id for _, p in repository.records] == [1]
    assert post.marked


async def test_posts_not_written_by_the_bot_are_never_acted_on():
    repository = FakeRepository(
        users={12: ["fan", {"source": "blacklist"}]},
        records=[(submission(details()), POST)],
    )
    post = FakePost("User ID: 12", from_bot=False)
    moderation = ModerateSubmission(repository, post, Mock())

    await moderation.remove()
    await moderation.lift_blacklist()

    assert len(repository.records) == 1
    assert not post.marked
    assert repository.lookups == []


async def test_blacklisting_and_lifting_keep_other_blacklist_entries():
    repository = FakeRepository(users={12: ["fan", {"other": "kept"}]})
    logger = Mock()
    moderation = ModerateSubmission(repository, FakePost("User ID: 12"), logger)

    await moderation.blacklist_submitter()
    assert repository.users[12][1] == {"other": "kept", "source": "blacklist"}
    await moderation.blacklist_submitter()
    logger.info.assert_called_with("User already blacklisted from adding sources")

    await moderation.lift_blacklist()
    assert repository.users[12][1] == {"other": "kept"}


async def test_blacklisting_an_unknown_user_changes_nothing():
    repository = FakeRepository()

    await ModerateSubmission(
        repository, FakePost("User ID: 12"), Mock()
    ).blacklist_submitter()

    assert repository.users == {}


@pytest.mark.parametrize(
    "content",
    ["User ID: 99\nUser ID: 12", "User ID", "User identifier: 99", "User ID: 1a"],
)
async def test_ambiguous_or_malformed_identity_is_rejected_before_lookup(content):
    repository = FakeRepository(users={99: ["x", None], 12: ["y", None]})
    moderation = ModerateSubmission(repository, FakePost(content), Mock())

    await moderation.blacklist_submitter()
    await moderation.lift_blacklist()

    assert repository.lookups == []


# Rendering and the Discord adapters


async def test_confirmation_post_flattens_user_fields_so_they_cannot_forge_an_id():
    content = confirmation_post(
        submission(details("https://a.co", "event\nUser ID: 99", None))
    )

    assert "Event: event User ID: 99" in content
    assert submitter_id(content) == 12


async def test_confirmation_prompt_lists_only_given_fields():
    assert confirmation_prompt(details(event="Show"), edit=True) == (
        "Event: Show\nEdit these fields?"
    )
    assert confirmation_prompt(
        details("https://a.co", None, date(2024, 1, 1)), edit=False
    ) == ("Source: https://a.co\nDate: 2024-01-01\nIs this correct?")


async def test_published_post_is_deleted_on_retract_and_reacted_to_on_open():
    message = SimpleNamespace(
        id=900, jump_url="jump", delete=AsyncMock(), add_reaction=AsyncMock()
    )
    bot = Mock()
    bot.get_channel.return_value.send = AsyncMock(return_value=message)
    posts = DiscordConfirmationPosts(bot, 2)

    assert await posts.publish(submission(details())) == PublishedPost(900, "jump")
    await posts.open_for_moderation(900)
    assert [c.args[0] for c in message.add_reaction.await_args_list] == [
        BotEmojis.CROSS,
        BotEmojis.HAMMER,
    ]
    await posts.retract(900)
    message.delete.assert_awaited_once()


async def test_refused_reactions_become_reactions_rejected():
    response = SimpleNamespace(status=403, reason="Forbidden")
    message = SimpleNamespace(
        id=900,
        jump_url="jump",
        add_reaction=AsyncMock(side_effect=discord.Forbidden(response, "no")),
    )
    bot = Mock()
    bot.get_channel.return_value.send = AsyncMock(return_value=message)
    posts = DiscordConfirmationPosts(bot, 2)
    await posts.publish(submission(details()))

    with pytest.raises(ReactionsRejected):
        await posts.open_for_moderation(900)


async def test_moderated_post_is_fetched_once_and_marked_deleted_once():
    message = SimpleNamespace(
        content="User ID: 12", author=SimpleNamespace(id=1), edit=AsyncMock()
    )
    bot = Mock()
    bot.user.id = 1
    bot.get_channel.return_value.fetch_message = AsyncMock(return_value=message)
    post = DiscordConfirmationPost(bot, 2, 900)

    assert await post.from_bot()
    assert await post.submitter_id() == 12
    await post.mark_deleted()
    message.content = message.edit.await_args.kwargs["content"]
    await post.mark_deleted()

    assert message.content == "User ID: 12\n\nDELETED"
    message.edit.assert_awaited_once()
    bot.get_channel.return_value.fetch_message.assert_awaited_once_with(900)
