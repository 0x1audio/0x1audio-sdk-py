from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

T = TypeVar("T", bound="MeFounding")


@_attrs_define
class MeFounding:
    """The account against the launch week's founding price

    Attributes:
        eligible (bool): This account gets Plus at the founding price (the same as Billing.founding and
            PlanAccess.founding)
        until (datetime.datetime | None): The cutoff, an instant; null until sign-up opens
        last_day (datetime.date | None): The cutoff's last day in Italy ("2026-11-18"); null until sign-up opens
    """

    eligible: bool
    until: datetime.datetime | None
    last_day: datetime.date | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        eligible = self.eligible

        until: None | str
        if isinstance(self.until, datetime.datetime):
            until = self.until.isoformat()
        else:
            until = self.until

        last_day: None | str
        if isinstance(self.last_day, datetime.date):
            last_day = self.last_day.isoformat()
        else:
            last_day = self.last_day

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "eligible": eligible,
                "until": until,
                "lastDay": last_day,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        eligible = d.pop("eligible")

        def _parse_until(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                until_type_0 = isoparse(data)

                return until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        until = _parse_until(d.pop("until"))

        def _parse_last_day(data: object) -> datetime.date | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_day_type_0 = isoparse(data).date()

                return last_day_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None, data)

        last_day = _parse_last_day(d.pop("lastDay"))

        me_founding = cls(
            eligible=eligible,
            until=until,
            last_day=last_day,
        )

        me_founding.additional_properties = d
        return me_founding

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
