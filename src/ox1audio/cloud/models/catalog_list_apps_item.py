from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="CatalogListAppsItem")


@_attrs_define
class CatalogListAppsItem:
    """
    Attributes:
        app_id (str):
        display_name (str):
        version (str):
        owner (str):
        repository (str):
        github (str):
        commit (str): The reviewed commit. The desktop installs exactly this commit.
        sponsored (bool):
        featured (bool): True when the committee is featuring this app. Installed copies stay off the Featured page.
        official (bool): True when the GitHub owner is the 0x1audio account.
        downloads (int): Accounts that installed this app, plus desktops that installed it while signed out.
        tags (list[str]):
        short_description (str):
        long_description (str):
    """

    app_id: str
    display_name: str
    version: str
    owner: str
    repository: str
    github: str
    commit: str
    sponsored: bool
    featured: bool
    official: bool
    downloads: int
    tags: list[str]
    short_description: str
    long_description: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        app_id = self.app_id

        display_name = self.display_name

        version = self.version

        owner = self.owner

        repository = self.repository

        github = self.github

        commit = self.commit

        sponsored = self.sponsored

        featured = self.featured

        official = self.official

        downloads = self.downloads

        tags = self.tags

        short_description = self.short_description

        long_description = self.long_description

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "appId": app_id,
                "displayName": display_name,
                "version": version,
                "owner": owner,
                "repository": repository,
                "github": github,
                "commit": commit,
                "sponsored": sponsored,
                "featured": featured,
                "official": official,
                "downloads": downloads,
                "tags": tags,
                "shortDescription": short_description,
                "longDescription": long_description,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        app_id = d.pop("appId")

        display_name = d.pop("displayName")

        version = d.pop("version")

        owner = d.pop("owner")

        repository = d.pop("repository")

        github = d.pop("github")

        commit = d.pop("commit")

        sponsored = d.pop("sponsored")

        featured = d.pop("featured")

        official = d.pop("official")

        downloads = d.pop("downloads")

        tags = cast(list[str], d.pop("tags"))

        short_description = d.pop("shortDescription")

        long_description = d.pop("longDescription")

        catalog_list_apps_item = cls(
            app_id=app_id,
            display_name=display_name,
            version=version,
            owner=owner,
            repository=repository,
            github=github,
            commit=commit,
            sponsored=sponsored,
            featured=featured,
            official=official,
            downloads=downloads,
            tags=tags,
            short_description=short_description,
            long_description=long_description,
        )

        catalog_list_apps_item.additional_properties = d
        return catalog_list_apps_item

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
