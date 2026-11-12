from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="TermsStanding")


@_attrs_define
class TermsStanding:
    """The account against the Terms of Service. Show the step while required is true.

    Attributes:
        current (None | str): The version in force ("1" for the beta, "2" from paid launch); null when this cloud has no
            Terms
        accepted (None | str): The latest version the account agreed to; null if it never agreed
        accepted_at (datetime.datetime | None): When it agreed to that version
        required (bool): True until the account agrees to the version in force. The desktop sign-in answers 409
            terms_required meanwhile
    """

    current: None | str
    accepted: None | str
    accepted_at: datetime.datetime | None
    required: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        current: None | str
        current = self.current

        accepted: None | str
        accepted = self.accepted

        accepted_at: None | str
        if isinstance(self.accepted_at, datetime.datetime):
            accepted_at = self.accepted_at.isoformat()
        else:
            accepted_at = self.accepted_at

        required = self.required

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current": current,
                "accepted": accepted,
                "acceptedAt": accepted_at,
                "required": required,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)

        def _parse_current(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        current = _parse_current(d.pop("current"))

        def _parse_accepted(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        accepted = _parse_accepted(d.pop("accepted"))

        def _parse_accepted_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                accepted_at_type_0 = isoparse(data)

                return accepted_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        accepted_at = _parse_accepted_at(d.pop("acceptedAt"))

        required = d.pop("required")

        terms_standing = cls(
            current=current,
            accepted=accepted,
            accepted_at=accepted_at,
            required=required,
        )

        terms_standing.additional_properties = d
        return terms_standing

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
