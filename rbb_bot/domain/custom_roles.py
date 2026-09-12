from dataclasses import dataclass


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
