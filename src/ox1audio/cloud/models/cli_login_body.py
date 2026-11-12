from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

from ..types import UNSET, Unset

T = TypeVar("T", bound="CliLoginBody")


@_attrs_define
class CliLoginBody:
    """
    Attributes:
        client (str | Unset): What signs in, shown to the person, like "mixel 0.3.0".
    """

    client: str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        client = self.client

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if client is not UNSET:
            field_dict["client"] = client

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        client = d.pop("client", UNSET)

        cli_login_body = cls(
            client=client,
        )

        return cli_login_body
