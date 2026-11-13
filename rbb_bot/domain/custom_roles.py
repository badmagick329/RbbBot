from dataclasses import dataclass

# Discord rejects role names longer than this.
ROLE_NAME_LIMIT = 100
# Upper bound administrators may set for custom roles per member.
MAX_ROLES_LIMIT = 5


@dataclass(frozen=True)
class RoleOwnership:
    role_id: int
    owner_id: int

    def permits_deletion(self, holder_ids, *, managed=False, default=False):
        """Ownership permits deletion only while the role has no other holders."""
        return (
            not managed
            and not default
            and all(holder_id == self.owner_id for holder_id in holder_ids)
        )
