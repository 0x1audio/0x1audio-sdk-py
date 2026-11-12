from enum import Enum


class SubmissionCreatedStatus(str, Enum):
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
