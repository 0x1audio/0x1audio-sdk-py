from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="DesktopHandoffBody")


@_attrs_define
class DesktopHandoffBody:
    """
    Attributes:
        state (str):
    """

    state: str

    def to_dict(self) -> dict[str, Any]:
        state = self.state

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        state = d.pop("state")

        desktop_handoff_body = cls(
            state=state,
        )

        return desktop_handoff_body
