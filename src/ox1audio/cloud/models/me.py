from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.me_status import MeStatus

if TYPE_CHECKING:
    from ..models.me_founding import MeFounding
    from ..models.me_waitlist_type_1 import MeWaitlistType1
    from ..models.terms_standing import TermsStanding


T = TypeVar("T", bound="Me")


@_attrs_define
class Me:
    """
    Attributes:
        status (MeStatus):
        terms (TermsStanding): The account against the Terms of Service. Show the step while required is true.
        founding (MeFounding): The account against the launch week's founding price
        waitlist (MeWaitlistType1 | None): Set while waitlisted; null once approved
    """

    status: MeStatus
    terms: TermsStanding
    founding: MeFounding
    waitlist: MeWaitlistType1 | None
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.me_waitlist_type_1 import MeWaitlistType1

        status = self.status.value

        terms = self.terms.to_dict()

        founding = self.founding.to_dict()

        waitlist: dict[str, Any] | None
        if isinstance(self.waitlist, MeWaitlistType1):
            waitlist = self.waitlist.to_dict()
        else:
            waitlist = self.waitlist

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "status": status,
                "terms": terms,
                "founding": founding,
                "waitlist": waitlist,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.me_founding import MeFounding
        from ..models.me_waitlist_type_1 import MeWaitlistType1
        from ..models.terms_standing import TermsStanding

        d = dict(src_dict)
        status = MeStatus(d.pop("status"))

        terms = TermsStanding.from_dict(d.pop("terms"))

        founding = MeFounding.from_dict(d.pop("founding"))

        def _parse_waitlist(data: object) -> MeWaitlistType1 | None:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                waitlist_type_1 = MeWaitlistType1.from_dict(data)

                return waitlist_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(MeWaitlistType1 | None, data)

        waitlist = _parse_waitlist(d.pop("waitlist"))

        me = cls(
            status=status,
            terms=terms,
            founding=founding,
            waitlist=waitlist,
        )

        me.additional_properties = d
        return me

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
