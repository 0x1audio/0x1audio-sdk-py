from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="VerifyBody")


@_attrs_define
class VerifyBody:
    """
    Attributes:
        email (str):
        code (str):
    """

    email: str
    code: str

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        code = self.code

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
                "code": code,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        email = d.pop("email")

        code = d.pop("code")

        verify_body = cls(
            email=email,
            code=code,
        )

        return verify_body
