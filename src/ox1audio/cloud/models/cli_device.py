from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CliDevice")


@_attrs_define
class CliDevice:
    """
    Attributes:
        device_code (str):
        user_code (str):  Example: CALM-RIVER-42.
        verification_url (str):
        interval (int):
        expires_in (int):
    """

    device_code: str
    user_code: str
    verification_url: str
    interval: int
    expires_in: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_code = self.device_code

        user_code = self.user_code

        verification_url = self.verification_url

        interval = self.interval

        expires_in = self.expires_in

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "device_code": device_code,
                "user_code": user_code,
                "verification_url": verification_url,
                "interval": interval,
                "expires_in": expires_in,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        device_code = d.pop("device_code")

        user_code = d.pop("user_code")

        verification_url = d.pop("verification_url")

        interval = d.pop("interval")

        expires_in = d.pop("expires_in")

        cli_device = cls(
            device_code=device_code,
            user_code=user_code,
            verification_url=verification_url,
            interval=interval,
            expires_in=expires_in,
        )

        cli_device.additional_properties = d
        return cli_device

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
