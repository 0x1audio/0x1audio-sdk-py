from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="SubmissionBody")


@_attrs_define
class SubmissionBody:
    """
    Attributes:
        repository (str):  Example: github.com/owner/repo.
        commit (str):
        branch (str | Unset):
        message (str | Unset):
    """

    repository: str
    commit: str
    branch: str | Unset = UNSET
    message: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        repository = self.repository

        commit = self.commit

        branch = self.branch

        message = self.message

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "repository": repository,
                "commit": commit,
            }
        )
        if branch is not UNSET:
            field_dict["branch"] = branch
        if message is not UNSET:
            field_dict["message"] = message

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        repository = d.pop("repository")

        commit = d.pop("commit")

        branch = d.pop("branch", UNSET)

        message = d.pop("message", UNSET)

        submission_body = cls(
            repository=repository,
            commit=commit,
            branch=branch,
            message=message,
        )

        return submission_body
