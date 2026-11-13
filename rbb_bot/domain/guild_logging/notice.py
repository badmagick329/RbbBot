from dataclasses import dataclass


@dataclass(frozen=True)
class GuildNotice:
    """Tell a guild's administrators that one of its configured actions failed for a reason only they can fix.

    A notice lands in a channel other members may read, so it holds fixed wording and
    Discord IDs only. Message content, member-authored text and Discord's exception text
    (which can echo either) never belong here; `identifiers` accepts integers alone so
    free text cannot slip in through them.

    `key` names the configuration problem, not the occurrence. It leaves out the member
    who triggered the failure so a join wave collapses into one notice.
    """

    key: str
    problem: str
    remedy: str
    identifiers: tuple[tuple[str, int], ...]

    def __post_init__(self):
        if not all(type(value) is int for _, value in self.identifiers):
            raise TypeError("Guild notice identifiers must be Discord IDs")
