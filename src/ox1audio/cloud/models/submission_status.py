from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.submission_status_status import SubmissionStatusStatus

if TYPE_CHECKING:
    from ..models.submission_status_checks_item import SubmissionStatusChecksItem
    from ..models.submission_status_notes_item import SubmissionStatusNotesItem


T = TypeVar("T", bound="SubmissionStatus")


@_attrs_define
class SubmissionStatus:
    """
    Attributes:
        id (str):
        app (str):
        version (str):
        status (SubmissionStatusStatus):
        created (datetime.datetime):
        commit (str):
        checks (list[SubmissionStatusChecksItem]):
        notes (list[SubmissionStatusNotesItem]):
    """

    id: str
    app: str
    version: str
    status: SubmissionStatusStatus
    created: datetime.datetime
    commit: str
    checks: list[SubmissionStatusChecksItem]
    notes: list[SubmissionStatusNotesItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        app = self.app

        version = self.version

        status = self.status.value

        created = self.created.isoformat()

        commit = self.commit

        checks = []
        for checks_item_data in self.checks:
            checks_item = checks_item_data.to_dict()
            checks.append(checks_item)

        notes = []
        for notes_item_data in self.notes:
            notes_item = notes_item_data.to_dict()
            notes.append(notes_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "app": app,
                "version": version,
                "status": status,
                "created": created,
                "commit": commit,
                "checks": checks,
                "notes": notes,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.submission_status_checks_item import SubmissionStatusChecksItem
        from ..models.submission_status_notes_item import SubmissionStatusNotesItem

        d = dict(src_dict)
        id = d.pop("id")

        app = d.pop("app")

        version = d.pop("version")

        status = SubmissionStatusStatus(d.pop("status"))

        created = isoparse(d.pop("created"))

        commit = d.pop("commit")

        checks = []
        _checks = d.pop("checks")
        for checks_item_data in _checks:
            checks_item = SubmissionStatusChecksItem.from_dict(checks_item_data)

            checks.append(checks_item)

        notes = []
        _notes = d.pop("notes")
        for notes_item_data in _notes:
            notes_item = SubmissionStatusNotesItem.from_dict(notes_item_data)

            notes.append(notes_item)

        submission_status = cls(
            id=id,
            app=app,
            version=version,
            status=status,
            created=created,
            commit=commit,
            checks=checks,
            notes=notes,
        )

        submission_status.additional_properties = d
        return submission_status

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
