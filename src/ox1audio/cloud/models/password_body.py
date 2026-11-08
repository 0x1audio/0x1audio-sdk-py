from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="PasswordBody")


@_attrs_define
class PasswordBody:
    """
    Attributes:
        email (str):
        proof (str):
        password (str):
        password_confirm (str):
    """

    email: str
    proof: str
    password: str
    password_confirm: str

    def to_dict(self) -> dict[str, Any]:
        email = self.email

        proof = self.proof

        password = self.password

        password_confirm = self.password_confirm

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "email": email,
                "proof": proof,
                "password": password,
                "passwordConfirm": password_confirm,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        email = d.pop("email")

        proof = d.pop("proof")

        password = d.pop("password")

        password_confirm = d.pop("passwordConfirm")

        password_body = cls(
            email=email,
            proof=proof,
            password=password,
            password_confirm=password_confirm,
        )

        return password_body
