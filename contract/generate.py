"""Generate everything that must agree from the one contract in this folder (GAB-37).

    python contract/generate.py            write every output
    python contract/generate.py --check    exit 1 and list what drifted (CI and tests run this)

Sources (this folder): app.schema.json, errors.json, permissions.json, protocol.json,
agents.md, llms.txt, digest.md (the MCP start tool's short rules).

Outputs:
    src/ox1audio/_contract.py                       the rules mixel check and the SDK read
    src/ox1audio/AGENTS.md                          what mixel new copies into every app
    src/ox1audio/docs/*.md, llms.txt                mixel docs, the MCP server, the docs site
    ../0x1audio-sdk-ts/src/contract.gen.ts          page SDK types
    ../0x1audio-cloud/apps/desktop/electron/apps/contract.gen.ts   desktop host types and rules
    ../0x1audio-{converter-app,hello-world-py-module}/AGENTS.md    official apps' copies (when present)

Every generated file is also checked for install lines that would run a stranger's package.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECTS = ROOT.parent
DOCS = "https://docs.0x1audio.com"
FORBIDDEN = ("uvx mixel", "npx mixel", "pip install mixel", "pipx install mixel")
AGENTS_BUDGET = 2000
LLMS_BUDGET = 1000
HEADER = "Generated from sdk-py/contract by contract/generate.py. Do not edit."


def load() -> dict:
    schema = json.loads((HERE / "app.schema.json").read_text())
    errors = json.loads((HERE / "errors.json").read_text())
    permissions = {k: v for k, v in json.loads((HERE / "permissions.json").read_text()).items() if not k.startswith("$")}
    protocol = json.loads((HERE / "protocol.json").read_text())
    sys.path.insert(0, str(ROOT / "src"))
    from ox1audio import __version__

    return {"schema": schema, "errors": {k: v for k, v in errors.items() if not k.startswith("$")}, "permissions": permissions, "protocol": protocol, "version": __version__}


def sdk_range(version: str) -> str:
    return "^" + ".".join(version.split(".")[:2])


# --- the rules, for Python --------------------------------------------------------------------


def rules(c: dict) -> dict:
    props = c["schema"]["properties"]
    window = props["window"]["properties"]
    reason = c["schema"]["$defs"]["reason"]
    hosts = props["permissions"]["properties"]["network"]["properties"]["hosts"]
    return {
        "SCHEMA": c["schema"]["$id"],
        "FIELDS": list(props),
        "REQUIRED": c["schema"]["required"],
        "PERMISSIONS": list(c["permissions"]),
        "PERMISSION_TEXT": {k: v["text"] for k, v in c["permissions"].items()},
        "NAME_PATTERN": props["name"]["pattern"],
        "NAME_LENGTH": [props["name"]["minLength"], props["name"]["maxLength"]],
        "DISPLAY_NAME_MAX": props["displayName"]["maxLength"],
        "SUMMARY_MAX": props["summary"]["maxLength"],
        "VERSION_PATTERN": props["version"]["pattern"],
        "SDK_PATTERN": props["sdk"]["pattern"],
        "ACCENT_PATTERN": props["accent"]["pattern"],
        "HOST_PATTERN": hosts["items"]["pattern"],
        "HOSTS_MAX": hosts["maxItems"],
        "REASON_LENGTH": [reason["minLength"], reason["maxLength"]],
        "WINDOW": {key: [value["minimum"], value["maximum"]] for key, value in window.items()},
        "TAGS_MAX": props["tags"]["maxItems"],
        "PROTOCOL": c["protocol"]["version"],
        "CONTROLS": c["protocol"]["controls"],
        "RUN_ERRORS": list(c["errors"]["run"]),
        "ERRORS": {code: {"area": area, "means": means, "fix": fix} for area, codes in c["errors"].items() for code, (means, fix) in codes.items()},
    }


def python_module(c: dict) -> str:
    lines = [f'"""{HEADER}\n\nThe app.json rules, permission codes, protocol version and error codes, in one place."""', ""]
    for key, value in rules(c).items():
        lines.append(f"{key} = {json.dumps(value, ensure_ascii=False, indent=None)}")
    return "\n".join(lines) + "\n"


# --- TypeScript -------------------------------------------------------------------------------


def typescript(c: dict, where: str) -> str:
    r = rules(c)
    run = " | ".join(json.dumps(code) for code in r["RUN_ERRORS"])
    controls = " | ".join(json.dumps(code) for code in r["CONTROLS"])
    accept = " | ".join(json.dumps(code) for code in c["protocol"]["accept"])
    permission = " | ".join(json.dumps(code) for code in r["PERMISSIONS"])
    shared = f"""// {HEADER}
// The action, error and Library item shapes that sdk-py (_protocol.py), the desktop host
// (electron/apps/protocol.ts) and the page SDK (@0x1audio/sdk/page) share. {where}

export const protocolVersion = {r['PROTOCOL']}
export const manifestSchema = {json.dumps(r['SCHEMA'])}

export type ErrorCode = {run}
export const errorCodes: readonly ErrorCode[] = {json.dumps(r['RUN_ERRORS'])}

export type PermissionCode = {permission}
export const permissionCodes: readonly PermissionCode[] = {json.dumps(r['PERMISSIONS'])}
export const permissionText: Record<PermissionCode, string> = {json.dumps(r['PERMISSION_TEXT'], ensure_ascii=False)}

export type Control = {controls}

// The "x-ox" hint on each input property: how Mixel draws the control.
export interface ControlHint {{
  control: Control
  accept?: {accept}
  multiple?: boolean
  label?: string
  placeholder?: string
  step?: number
}}

export interface PropertySchema {{
  type?: "string" | "number" | "integer" | "boolean" | "array"
  title?: string
  default?: unknown
  enum?: string[]
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  minItems?: number
  items?: {{ type: "string"; enum?: string[] }}
  uniqueItems?: boolean
  anyOf?: PropertySchema[]
  "x-ox"?: ControlHint
}}

export interface InputSchema {{
  type: "object"
  properties: Record<string, PropertySchema>
  required: string[]
  additionalProperties: false
}}

// One @ox.action, as the worker declares it in its ready line.
export interface ActionSpec {{
  name: string
  title: string
  input: InputSchema
  timeout: number
}}

// A Library item an action made (results, and what Stop kept).
export interface Item {{
  id?: string
  kind?: string
  title?: string
  path?: string
}}

export interface ErrorBody {{
  code: ErrorCode
  message: string
  hint?: string
  detail?: string
  // On "cancelled": what the action finished before Stop. Already in the Library.
  kept?: Item[]
}}
"""
    if "desktop" in where.lower():
        shared += f"""
// app.json rules (the desktop's schema.ts reads these; a test fails if they drift).
export const manifestRules = {json.dumps({k: r[k] for k in ("FIELDS", "NAME_PATTERN", "VERSION_PATTERN", "SDK_PATTERN", "ACCENT_PATTERN", "HOST_PATTERN", "REASON_LENGTH", "WINDOW", "TAGS_MAX")}, indent=2)} as const

export const limits = {{ line: {c['protocol']['lineLimit']}, result: {c['protocol']['resultLimit']}, event: {c['protocol']['eventLimit']}, progressPerSecond: {c['protocol']['progressPerSecond']} }} as const
"""
    return shared


# --- docs -------------------------------------------------------------------------------------


def agents(c: dict) -> str:
    text = (HERE / "agents.md").read_text()
    listed = ", ".join(f"`{code}` ({info['short']})" for code, info in c["permissions"].items() if info.get("short"))
    return text.replace("{{schema}}", c["schema"]["$id"]).replace("{{sdk_range}}", sdk_range(c["version"])).replace("{{permission_list}}", listed)


def app_json_doc(c: dict) -> str:
    schema = c["schema"]
    rows = []
    for name, prop in schema["properties"].items():
        need = "required" if name in schema["required"] else ("entry or page" if name in ("entry", "page") else "optional")
        rows.append(f"| `{name}` | {need} | {prop.get('description', '')} |")
    window = schema["properties"]["window"]["properties"]
    sizes = ", ".join(f"`{k}` {v['minimum']}–{v['maximum']}" for k, v in window.items())
    return "\n".join([
        "# app.json", "",
        f"Every app has an `app.json` at the top of its folder. `$schema` is `{schema['$id']}`; editors use it for autocomplete. Unknown fields are errors. `mixel check` applies these rules, and so do Mixel and the registry.", "",
        "| Field | | Rule |", "| --- | --- | --- |", *rows, "",
        f"Window sizes in pixels: {sizes}. Reasons are {schema['$defs']['reason']['minLength']} to {schema['$defs']['reason']['maxLength']} characters.",
        "",
    ])


def errors_doc(c: dict) -> str:
    titles = {"check": "From mixel check (and the registry)", "run": "When an action runs (pages see these as OxError.code)", "cli": "From the mixel command"}
    lines = ["# Errors", "", "Every error has a code, what happened, and the fix. The message you see names the exact fix for your case; this page is the index.", ""]
    for area, codes in c["errors"].items():
        lines += [f"## {titles[area]}", "", "| Code | Means | Usual fix |", "| --- | --- | --- |"]
        lines += [f"| `{code}` | {means} | {fix.replace('|', '/')} |" for code, (means, fix) in codes.items()]
        lines.append("")
    return "\n".join(lines)


def permissions_doc(c: dict) -> str:
    lines = ["# Permissions", "", "An app asks only for what its code uses, each with one sentence that says why. Declared is binding: Mixel refuses anything else. The install sheet shows the words below and the app's reason.", "",
             "| Code | The person reads | Needed for |", "| --- | --- | --- |"]
    lines += [f"| `{code}` | {info['text']} | {info['uses']} |" for code, info in c["permissions"].items()]
    return "\n".join(lines + ["", '`network` is `{"why": "…", "hosts": ["example.com"]}`. The whole web, IPs and localhost are refused.', ""])


def protocol_doc(c: dict) -> str:
    p = c["protocol"]
    lines = ["# Protocol", "", p["$comment"], "", "## Worker to Mixel", "", "| type | Fields | Notes |", "| --- | --- | --- |"]
    lines += [f"| `{kind}` | `{fields}` | {note} |" for kind, (fields, note) in p["workerToHost"].items()]
    lines += ["", "## Mixel to worker", "", "| type | Fields | Notes |", "| --- | --- | --- |"]
    lines += [f"| `{kind}` | `{fields}` | {note} |" for kind, (fields, note) in p["hostToWorker"].items()]
    lines += ["", "## Types", ""] + [f"- `{name}` = `{shape}`" for name, shape in p["types"].items()]
    lines += ["", f"Limits: a line or a result is at most {p['lineLimit'] // 1048576} MiB, an event body {p['eventLimit'] // 1024} KiB; progress is coalesced to {p['progressPerSecond']} a second.", ""]
    return "\n".join(lines)


def cli_doc() -> str:
    from ox1audio.cli import _SECTIONS
    from ox1audio.cli.out import AUTH, FAILED, NETWORK, OK, USAGE

    lines = ["# The mixel command", "", "Install or update it with `uv tool install ox1audio`. It runs on macOS, Linux and Windows.", ""]
    for title, items in _SECTIONS:
        lines += [f"## {title}", "", "| Command | Does | Options |", "| --- | --- | --- |"]
        lines += [f"| `mixel {name}` | {text} | {('`' + flags + '`') if flags else ''} |" for name, text, flags in items]
        lines.append("")
    lines += [f"Exit codes: {OK} ok, {FAILED} a check or test failed, {USAGE} usage, {AUTH} sign-in, {NETWORK} network or registry. `--json` prints one JSON object for tools.", ""]
    return "\n".join(lines)


def llms(c: dict) -> str:
    return (HERE / "llms.txt").read_text().replace("{{docs}}", DOCS)


# --- write or check ---------------------------------------------------------------------------


def outputs() -> dict[Path, str]:
    c = load()
    pkg = ROOT / "src" / "ox1audio"
    found = {
        pkg / "_contract.py": python_module(c),
        pkg / "AGENTS.md": agents(c),
        pkg / "docs" / "agents.md": agents(c),
        pkg / "docs" / "app-json.md": app_json_doc(c),
        pkg / "docs" / "errors.md": errors_doc(c),
        pkg / "docs" / "permissions.md": permissions_doc(c),
        pkg / "docs" / "protocol.md": protocol_doc(c),
        pkg / "docs" / "cli.md": cli_doc(),
        pkg / "docs" / "llms.txt": llms(c),
        pkg / "docs" / "digest.md": (HERE / "digest.md").read_text(),
        pkg / "app.schema.json": json.dumps(c["schema"], indent=2, ensure_ascii=False) + "\n",
    }
    ts = PROJECTS / "0x1audio-sdk-ts" / "src"
    if ts.is_dir():
        found[ts / "contract.gen.ts"] = typescript(c, "Page SDK copy.")
    desktop = PROJECTS / "0x1audio-cloud" / "apps" / "desktop" / "electron" / "apps"
    if desktop.is_dir():
        found[desktop / "contract.gen.ts"] = typescript(c, "Desktop copy.")
    for app in ("0x1audio-converter-app", "0x1audio-hello-world-py-module"):
        if (PROJECTS / app / "AGENTS.md").is_file():
            found[PROJECTS / app / "AGENTS.md"] = agents(c)
    return found


def tokens(text: str) -> tuple[int, str]:
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text)), "cl100k"
    except ImportError:
        return round(len(text.encode()) * 0.28), "estimated from bytes"


def problems(found: dict[Path, str]) -> list[str]:
    issues = []
    for path, text in found.items():
        for bad in FORBIDDEN:
            if bad in text:
                issues.append(f"{path.name} says `{bad}`, which would run a stranger's package. Use `uv tool install ox1audio`.")
    agents_tokens, how = tokens(found[ROOT / "src" / "ox1audio" / "AGENTS.md"])
    if agents_tokens > AGENTS_BUDGET:
        issues.append(f"AGENTS.md is {agents_tokens} tokens ({how}), over its {AGENTS_BUDGET} budget.")
    llms_tokens, how = tokens(found[ROOT / "src" / "ox1audio" / "docs" / "llms.txt"])
    if llms_tokens > LLMS_BUDGET:
        issues.append(f"llms.txt is {llms_tokens} tokens ({how}), over its {LLMS_BUDGET} budget.")
    return issues


def main(argv: list[str]) -> int:
    found = outputs()
    issues = problems(found)
    if "--check" in argv:
        drift = [path for path, text in found.items() if not path.is_file() or path.read_text() != text]
        for path in drift:
            issues.append(f"{path} is out of date. Run: python contract/generate.py")
        for line in issues:
            print(line, file=sys.stderr)
        return 1 if issues else 0
    if issues:
        for line in issues:
            print(line, file=sys.stderr)
        return 1
    for path, text in found.items():
        if path.is_file() and path.read_text() == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path.relative_to(PROJECTS)}")
    agents_tokens, how = tokens(found[ROOT / "src" / "ox1audio" / "AGENTS.md"])
    llms_tokens, _ = tokens(found[ROOT / "src" / "ox1audio" / "docs" / "llms.txt"])
    print(f"AGENTS.md {agents_tokens}/{AGENTS_BUDGET} tokens, llms.txt {llms_tokens}/{LLMS_BUDGET} ({how})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
