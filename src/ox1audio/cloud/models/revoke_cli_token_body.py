from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar
from uuid import UUID

from attrs import define as _attrs_define

T = TypeVar("T", bound="RevokeCliTokenBody")


@_attrs_define
class RevokeCliTokenBody:
    """
    Attributes:
        id (UUID):
    """

    id: UUID

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "id": id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        revoke_cli_token_body = cls(
            id=id,
        )

        return revoke_cli_token_body
