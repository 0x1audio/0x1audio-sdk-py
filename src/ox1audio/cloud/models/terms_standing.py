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
    """The account against the Terms of Service. Show the step while required is true. Two versions are kept apart:
    current, the one in force (the step offers it, each checkout records it), and minimum, the oldest one an account can
    have agreed to and still use the cloud.

        Attributes:
            current (None | str): The version in force ("1" for the beta, "2" from paid launch): the step asks for it, and a
                checkout records it as the version the buyer agreed to on the Choose sheet. Null when this cloud has no Terms
            accepted (None | str): The latest version the account agreed to in the step; null if it never agreed there. An
                agreement given with a purchase is kept with the purchase (the export's billing), not here
            accepted_at (datetime.datetime | None): When it agreed to that version
            required (bool): True until the account has agreed to a version that's enough to use the cloud (minimum or
                later, in the step or with a purchase), having been through the step once. The desktop sign-in and mixel login
                answer terms_required meanwhile
            minimum (None | str): The oldest version that lets an account use the cloud now: TERMS_REQUIRED_VERSION, else
                current, and current from requiredFrom. Null when this cloud has no Terms
            required_from (datetime.datetime | None): When current becomes the minimum (TERMS_REQUIRED_FROM): a material
                change takes effect then, 30 days or more after its email (Terms §14). Null when no such change is set
            review (bool): A material change is on its way (before requiredFrom) and this account hasn't agreed to current
                yet: offer "Review the new Terms" with Not now. It becomes required at requiredFrom
    """

    current: None | str
    accepted: None | str
    accepted_at: datetime.datetime | None
    required: bool
    minimum: None | str
    required_from: datetime.datetime | None
    review: bool
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

        minimum: None | str
        minimum = self.minimum

        required_from: None | str
        if isinstance(self.required_from, datetime.datetime):
            required_from = self.required_from.isoformat()
        else:
            required_from = self.required_from

        review = self.review

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "current": current,
                "accepted": accepted,
                "acceptedAt": accepted_at,
                "required": required,
                "minimum": minimum,
                "requiredFrom": required_from,
                "review": review,
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

        def _parse_minimum(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        minimum = _parse_minimum(d.pop("minimum"))

        def _parse_required_from(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                required_from_type_0 = isoparse(data)

                return required_from_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        required_from = _parse_required_from(d.pop("requiredFrom"))

        review = d.pop("review")

        terms_standing = cls(
            current=current,
            accepted=accepted,
            accepted_at=accepted_at,
            required=required,
            minimum=minimum,
            required_from=required_from,
            review=review,
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
