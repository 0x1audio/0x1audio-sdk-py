from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ProblemDetail")


@_attrs_define
class ProblemDetail:
    """
    Attributes:
        code (str):
        message (str):
        param (str | Unset):
        fix (str | Unset):
        doc_url (str | Unset):
    """

    code: str
    message: str
    param: str | Unset = UNSET
    fix: str | Unset = UNSET
    doc_url: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        code = self.code

        message = self.message

        param = self.param

        fix = self.fix

        doc_url = self.doc_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "code": code,
                "message": message,
            }
        )
        if param is not UNSET:
            field_dict["param"] = param
        if fix is not UNSET:
            field_dict["fix"] = fix
        if doc_url is not UNSET:
            field_dict["doc_url"] = doc_url

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        code = d.pop("code")

        message = d.pop("message")

        param = d.pop("param", UNSET)

        fix = d.pop("fix", UNSET)

        doc_url = d.pop("doc_url", UNSET)

        problem_detail = cls(
            code=code,
            message=message,
            param=param,
            fix=fix,
            doc_url=doc_url,
        )

        problem_detail.additional_properties = d
        return problem_detail

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
