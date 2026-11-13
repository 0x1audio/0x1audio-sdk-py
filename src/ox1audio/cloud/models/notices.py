from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Notices")


@_attrs_define
class Notices:
    """The emails about Mixel itself this account can turn off (W10). Purchase, withdrawal and account emails always go

    Attributes:
        plus_on_sale (bool): The "Plus is on sale" email; on unless turned off
    """

    plus_on_sale: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plus_on_sale = self.plus_on_sale

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "plusOnSale": plus_on_sale,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        plus_on_sale = d.pop("plusOnSale")

        notices = cls(
            plus_on_sale=plus_on_sale,
        )

        notices.additional_properties = d
        return notices

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
