"""app.json v1, checked the way 0x1audio reads it. Used by ``mixel check``.

The rules (fields, patterns, limits, permission codes) come from the contract
(sdk-py/contract, generated into _contract.py), as do the desktop's.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ox1audio import _contract as rules

SCHEMA = rules.SCHEMA
DOCS = "https://docs.0x1audio.com"
CODES = tuple(rules.PERMISSIONS)
FIELDS = tuple(rules.FIELDS)
_name = re.compile(rules.NAME_PATTERN)
_version = re.compile(rules.VERSION_PATTERN)
_range = re.compile(rules.SDK_PATTERN)
_accent = re.compile(rules.ACCENT_PATTERN)
_host = re.compile(rules.HOST_PATTERN)


@dataclass
class Finding:
    code: str
    where: str
    message: str
    fix: str
    anchor: str
    # "error" or "warn". Left out, it is the code's severity in contract/errors.json.
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            self.severity = rules.ERRORS.get(self.code, {}).get("severity", "error")

    @property
    def doc(self) -> str:
        # anchor is "page#section", or a section of the app.json page.
        return f"{DOCS}/{self.anchor if '#' in self.anchor or '/' in self.anchor else 'app-json#' + self.anchor}"

    def json(self) -> dict:
        return {"code": self.code, "severity": self.severity, "where": self.where, "message": self.message, "fix": self.fix, "doc": self.doc}


@dataclass
class Manifest:
    data: dict
    findings: list[Finding] = field(default_factory=list)

    @property
    def permissions(self) -> set[str]:
        value = self.data.get("permissions")
        return set(value) if isinstance(value, dict) else set(value) if isinstance(value, list) else set()


def check(folder: Path) -> Manifest:
    path = folder / "app.json"
    if not path.is_file():
        return Manifest({}, [Finding("manifest_missing", "app.json", "There is no app.json in this folder.", 'run mixel new "My App" to start one', "fields")])
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        return Manifest({}, [Finding("manifest_json", f"app.json:{error.lineno}", f"app.json is not valid JSON: {error.msg}.", "fix the JSON at that line", "fields")])
    if not isinstance(data, dict):
        return Manifest({}, [Finding("manifest_json", "app.json", "app.json must be an object.", f'start from {{ "$schema": "{SCHEMA}", ... }}', "fields")])
    found: list[Finding] = []

    def bad(code: str, where: str, message: str, fix: str, anchor: str = "fields", severity: str = "") -> None:
        found.append(Finding(code, f"app.json › {where}" if where else "app.json", message, fix, anchor, severity))

    if "$schema" not in data:
        bad("manifest_v0", "", 'app.json has no "$schema", so 0x1audio reads it as v0. v0 still loads, until 0.5.',
            f'add "$schema": "{SCHEMA}", "sdk": "^0.3", rename worker.entry to entry and frontend to page, and give each permission a reason', "v1")
        return Manifest(data, found)
    if data["$schema"] != SCHEMA:
        bad("manifest_schema", "$schema", f"$schema is {json.dumps(data['$schema'])}, which this SDK doesn't read.", f'"$schema": "{SCHEMA}"')
    moved = {"worker": ("worker is now entry", '"entry": "app.py"'), "frontend": ("frontend is now page", '"page": "dist/index.html"'),
             "dependencies": ("dependencies is not a field: Python packages go in pyproject.toml", "delete it"), "cloud": ("cloud is not a field", "delete it")}
    for key in data:
        if key in moved:
            bad("manifest_field", key, moved[key][0] + ".", moved[key][1])
        elif key not in FIELDS:
            bad("manifest_field", key, f"{key} is not a field.", f"remove it; the fields are {', '.join(FIELDS)}")
    name = data.get("name")
    if not isinstance(name, str) or not rules.NAME_LENGTH[0] <= len(name) <= rules.NAME_LENGTH[1] or not _name.match(name):
        bad("manifest_name", "name", "name is 2 to 48 lowercase letters, digits and dashes, and never changes.", f'"name": "{_slug(str(data.get("displayName") or "my-app"))}"')
    display = data.get("displayName")
    if not isinstance(display, str) or not display.strip() or len(display) > rules.DISPLAY_NAME_MAX:
        bad("manifest_display_name", "displayName", "displayName is the name people see, up to 48 characters.", '"displayName": "My App"')
    if "summary" in data and (not isinstance(data["summary"], str) or not data["summary"].strip() or len(data["summary"]) > rules.SUMMARY_MAX):
        bad("manifest_summary", "summary", "summary is one sentence, up to 80 characters.", '"summary": "One file to many formats at once."')
    if not isinstance(data.get("version"), str) or not _version.match(data["version"]):
        bad("manifest_version", "version", "version is MAJOR.MINOR.PATCH.", '"version": "0.1.0"')
    sdk = data.get("sdk")
    if sdk is None:
        bad("sdk_missing", "sdk", "sdk is required: it says which 0x1audio can run this app.", '"sdk": "^0.3"', "sdk")
    elif not isinstance(sdk, str) or not _range.match(sdk):
        bad("sdk_range", "sdk", f"sdk {json.dumps(sdk)} is not a caret range.", '"sdk": "^0.3"', "sdk")
    else:
        from ox1audio import __version__

        if not accepts(sdk, __version__):
            bad("sdk_range", "sdk", f"sdk {sdk} doesn't include this SDK ({__version__}).", f'"sdk": "^{".".join(__version__.split(".")[:2])}"', "sdk")
    entry, page = data.get("entry"), data.get("page")
    if entry is None and page is None:
        bad("manifest_entry", "entry", "The app needs an entry (the Python file with your actions).", '"entry": "app.py"')
    if entry is not None:
        if not isinstance(entry, str) or not entry.endswith(".py") or ".." in Path(entry).parts or Path(entry).is_absolute():
            bad("manifest_entry", "entry", "entry is a .py file inside the app.", '"entry": "app.py"')
        elif not (folder / entry).is_file():
            bad("manifest_entry", "entry", f"{entry} is missing.", "point entry at the Python file with your actions")
    if page is not None:
        if not isinstance(page, str) or not page.endswith(".html") or ".." in Path(page).parts:
            bad("manifest_page", "page", "page is an .html file inside the app, built by Vite.", '"page": "dist/index.html"', "page")
        elif not (folder / page).is_file():
            bad("manifest_page", "page", f"{page} is missing.", "build the page (npm run build)", "page")
    permissions = data.get("permissions", {})
    if isinstance(permissions, list):
        example = f'{{ "{permissions[0]}": "Why the app needs it, in one sentence." }}' if permissions else "{}"
        bad("permission_reason", "permissions", "permissions is an object of code → reason, not a list.", f'"permissions": {example}', "permissions")
    elif not isinstance(permissions, dict):
        bad("permission_reason", "permissions", "permissions is an object of code → reason.", '"permissions": { "files": "Open the songs you choose." }', "permissions")
    else:
        for code, reason in permissions.items():
            if code not in CODES:
                bad("permission_unknown", f"permissions.{code}", f"{code} is not a permission.", f"use {', '.join(CODES)}", "permissions")
                continue
            if code == "network":
                if not isinstance(reason, dict):
                    bad("network_hosts", "permissions.network", "network says why, and which hosts.", '"network": { "why": "Download the model once.", "hosts": ["github.com"] }', "network")
                    continue
                reason, hosts = reason.get("why"), reason.get("hosts")
                if not isinstance(hosts, list) or not hosts or len(hosts) > rules.HOSTS_MAX or any(not isinstance(h, str) or not _host.match(h) or h == "localhost" or re.fullmatch(r"[0-9.]+", h) for h in hosts):
                    bad("network_hosts", "permissions.network.hosts", "hosts lists the domains the app reaches. The whole web, IPs and localhost are refused.", '"hosts": ["github.com"]', "network")
            low, high = rules.REASON_LENGTH
            if not isinstance(reason, str) or not low <= len(reason.strip()) <= high:
                bad("permission_reason", f"permissions.{code}", "Each permission has a reason the person reads: one sentence, 12 to 120 characters.", f'"{code}": "{_example_reason(code)}"', "permissions")
    if "accent" in data and (not isinstance(data["accent"], str) or not _accent.match(data["accent"])):
        bad("manifest_accent", "accent", "accent is a colour like #3366ff.", '"accent": "#5b8cff"')
    icon = data.get("icon")
    if icon is not None and (not isinstance(icon, str) or not icon.lower().endswith((".svg", ".png")) or not (folder / icon).is_file()):
        bad("manifest_icon", "icon", "icon is a square .svg or .png inside the app.", '"icon": "icon.svg"')
    window = data.get("window")
    if window is not None:
        sizes = window if isinstance(window, dict) else {}
        wrong = [key for key, value in sizes.items() if key not in rules.WINDOW or isinstance(value, bool) or not isinstance(value, int) or not rules.WINDOW[key][0] <= value <= rules.WINDOW[key][1]]
        if not isinstance(window, dict) or not window or wrong:
            ranges = ", ".join(f"{key} {low}-{high}" for key, (low, high) in rules.WINDOW.items())
            bad("manifest_window", f"window.{wrong[0]}" if wrong else "window", f"window sizes are whole pixels: {ranges}.", '"window": { "width": 900, "height": 640 }')
    tags = data.get("tags")
    if tags is not None and (not isinstance(tags, list) or len(tags) > rules.TAGS_MAX or any(not isinstance(tag, str) or not tag or len(tag) > 64 or re.search(r"\s", tag) for tag in tags)):
        bad("manifest_tags", "tags", f"tags is up to {rules.TAGS_MAX} single words.", '"tags": ["convert"]')
    return Manifest(data, found)


def accepts(range_: str, version: str) -> bool:
    want = re.fullmatch(r"\^(\d+)\.(\d+)(?:\.(\d+))?", range_)
    have = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not want or not have:
        return False
    major, minor, patch = int(want[1]), int(want[2]), int(want[3] or 0)
    a, b, c = int(have[1]), int(have[2]), int(have[3])
    if a != major:
        return False
    if major == 0:
        return b == minor and c >= patch
    return b > minor or (b == minor and c >= patch)


def _example_reason(code: str) -> str:
    return {
        "files": "Open the songs you choose and save the results next to them.",
        "library": "Save the results to your Library.",
        "data": "Remember your presets on this computer.",
        "network": "Download the model once.",
    }.get(code, "Why the app needs it, in one sentence.")


def _slug(title: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in title).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "app"
