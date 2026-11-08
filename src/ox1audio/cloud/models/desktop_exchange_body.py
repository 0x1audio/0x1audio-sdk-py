from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="DesktopExchangeBody")


@_attrs_define
class DesktopExchangeBody:
    """
    Attributes:
        code (str):
        state (str):
    """

    code: str
    state: str

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        state = self.state

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "code": code,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        code = d.pop("code")

        state = d.pop("state")

        desktop_exchange_body = cls(
            code=code,
            state=state,
        )

        return desktop_exchange_body
