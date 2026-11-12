from enum import Enum


class SubmissionStatusStatus(str, Enum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    REJECTED = "rejected"

    def __str__(self) -> str:
        return str(self.value)
