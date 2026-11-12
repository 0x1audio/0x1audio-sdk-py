from enum import Enum


class MeStatus(str, Enum):
    APPROVED = "approved"
    WAITLISTED = "waitlisted"

    def __str__(self) -> str:
        return str(self.value)
