from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="CliPollBody")


@_attrs_define
class CliPollBody:
    """
    Attributes:
        device_code (str):
    """

    device_code: str

    def to_dict(self) -> dict[str, Any]:
        device_code = self.device_code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "device_code": device_code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        device_code = d.pop("device_code")

        cli_poll_body = cls(
            device_code=device_code,
        )

        return cli_poll_body
