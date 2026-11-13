from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.cli_token_account import CliTokenAccount


T = TypeVar("T", bound="CliToken")


@_attrs_define
class CliToken:
    """
    Attributes:
        token (str):
        account (CliTokenAccount):
    """

    token: str
    account: CliTokenAccount
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        token = self.token

        account = self.account.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "token": token,
                "account": account,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.cli_token_account import CliTokenAccount

        d = dict(src_dict)
        token = d.pop("token")

        account = CliTokenAccount.from_dict(d.pop("account"))

        cli_token = cls(
            token=token,
            account=account,
        )

        cli_token.additional_properties = d
        return cli_token

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
