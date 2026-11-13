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
    ../0x1audio-cloud/apps/desktop/schema/app.schema.json          the editor schema
    ../0x1audio-{converter-app,hello-world-py-module}/AGENTS.md    official apps' copies (when present)

Every generated file is also checked for install lines that would run a stranger's package.
"""

from __future__ import annotations

import json
import re
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
        "LICENSE_PATTERN": props["license"]["pattern"],
        "PROTOCOL": c["protocol"]["version"],
        "CONTROLS": c["protocol"]["controls"],
        "RUN_ERRORS": list(c["errors"]["run"]),
        "ERRORS": {code: {"area": area, "means": entry[0], "fix": entry[1], "severity": entry[2] if len(entry) > 2 else "error"} for area, codes in c["errors"].items() for code, entry in codes.items()},
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
  // Shown after the value, like "dB", "Hz" or "%".
  unit?: string
  // A slider's "no change" value when it isn't the minimum (0 on a -12…12 slider):
  // the track fills from here to the value, with a mark at the origin.
  origin?: number
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
  maxItems?: number
  // Files and choices are strings; a range (control "slider", 2 items) is numbers.
  items?: {{ type: "string" | "number" | "integer"; enum?: string[]; minimum?: number; maximum?: number }}
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
export const manifestRules = {json.dumps({k: r[k] for k in ("FIELDS", "NAME_PATTERN", "NAME_LENGTH", "DISPLAY_NAME_MAX", "SUMMARY_MAX", "VERSION_PATTERN", "SDK_PATTERN", "ACCENT_PATTERN", "HOST_PATTERN", "HOSTS_MAX", "REASON_LENGTH", "WINDOW", "TAGS_MAX", "LICENSE_PATTERN")}, indent=2)} as const

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
    titles = {"check": "From mixel check (and the registry)", "run": "When an action runs (pages see these as OxError.code)", "cli": "From the mixel command",
              "library": "From the person's Library (mixel mcp, ox1audio.local and Mixel's own assistant tools)",
              "registry": "From the registry and the cloud (mixel login, publish and status)"}
    lines = ["# Errors", "", "Every error has a code, what happened, and the fix. The message you see names the exact fix for your case; this page is the index. Codes marked (warning) don't fail `mixel check`, but `--strict` and publish refuse them too.", ""]
    for area, codes in c["errors"].items():
        lines += [f"## {titles[area]}", "", "| Code | Means | Usual fix |", "| --- | --- | --- |"]
        lines += [f"| `{code}`{' (warning)' if entry[2:] == ['warn'] else ''} | {entry[0]} | {entry[1].replace('|', '/')} |" for code, entry in codes.items()]
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


# --- Go, for the registry (GAB-56) -------------------------------------------------------------

GO_TEMPLATE = """// Code generated from sdk-py/contract by contract/generate.py. DO NOT EDIT.

// Package appmanifest checks app.json v1 with the same rules as mixel check and the desktop.
// It covers what can be checked from app.json alone; file checks (entry exists, icon is
// square) and code checks (permissions used) stay with mixel check, which the registry runs.
package appmanifest

import (
\t"encoding/json"
\t"fmt"
\t"net"
\t"regexp"
\t"strings"
)

const Schema = %(schema)s
const DocsURL = "https://docs.0x1audio.com/errors#"

var Fields = %(fields)s
var PermissionCodes = %(codes)s

var (
\tnamePattern    = regexp.MustCompile(%(name)s)
\tversionPattern = regexp.MustCompile(%(version)s)
\tsdkPattern     = regexp.MustCompile(%(sdk)s)
\taccentPattern  = regexp.MustCompile(%(accent)s)
\thostPattern    = regexp.MustCompile(%(host)s)
)

const (
\tnameMin, nameMax     = %(name_min)d, %(name_max)d
\tdisplayNameMax       = %(display)d
\tsummaryMax           = %(summary)d
\treasonMin, reasonMax = %(reason_min)d, %(reason_max)d
\thostsMax             = %(hosts_max)d
\thostMax              = %(host_len)d
\ttagsMax              = %(tags_max)d
)

var windowBounds = map[string][2]int{%(window)s}

// fixes is each code's usual fix, from contract/errors.json.
var fixes = map[string]string{%(fixes)s}

// Problem is one refusal, in the registry's error shape: {code, message, param, doc_url, fix}.
type Problem struct {
\tCode    string `json:"code"`
\tMessage string `json:"message"`
\tParam   string `json:"param,omitempty"`
\tFix     string `json:"fix,omitempty"`
\tDocURL  string `json:"doc_url"`
}

func problem(code, param, message string) Problem {
\treturn Problem{Code: code, Message: message, Param: param, Fix: fixes[code], DocURL: DocsURL + code}
}

// Validate returns every problem with an app.json, or nil when it is a valid v1 manifest.
func Validate(raw []byte) []Problem {
\tvar data map[string]any
\tif err := json.Unmarshal(raw, &data); err != nil || data == nil {
\t\treturn []Problem{problem("manifest_json", "", "app.json is not a JSON object.")}
\t}
\tvar found []Problem
\tadd := func(code, param, message string) { found = append(found, problem(code, param, message)) }
\tschema, ok := data["$schema"]
\tif !ok {
\t\treturn []Problem{problem("manifest_v0", "$schema", "app.json has no \\"$schema\\": it is the old v0 format.")}
\t}
\tif schema != Schema {
\t\tadd("manifest_schema", "$schema", fmt.Sprintf("$schema is %%v, which isn't the v1 URL.", schema))
\t}
\tknown := map[string]bool{}
\tfor _, field := range Fields {
\t\tknown[field] = true
\t}
\tfor key := range data {
\t\tif !known[key] {
\t\t\tadd("manifest_field", key, key+" is not a field.")
\t\t}
\t}
\tif name, ok := data["name"].(string); !ok || len(name) < nameMin || len(name) > nameMax || !namePattern.MatchString(name) {
\t\tadd("manifest_name", "name", fmt.Sprintf("name is %%d to %%d lowercase letters, digits and dashes.", nameMin, nameMax))
\t}
\tif display, ok := data["displayName"].(string); !ok || strings.TrimSpace(display) == "" || len([]rune(display)) > displayNameMax {
\t\tadd("manifest_display_name", "displayName", fmt.Sprintf("displayName is the name people see, up to %%d characters.", displayNameMax))
\t}
\tif value, present := data["summary"]; present {
\t\tif summary, ok := value.(string); !ok || strings.TrimSpace(summary) == "" || len([]rune(summary)) > summaryMax {
\t\t\tadd("manifest_summary", "summary", fmt.Sprintf("summary is one sentence, up to %%d characters.", summaryMax))
\t\t}
\t}
\tif version, ok := data["version"].(string); !ok || !versionPattern.MatchString(version) {
\t\tadd("manifest_version", "version", "version is MAJOR.MINOR.PATCH.")
\t}
\tif value, present := data["sdk"]; !present {
\t\tadd("sdk_missing", "sdk", "sdk is required: it says which Mixel can run this app.")
\t} else if sdk, ok := value.(string); !ok || !sdkPattern.MatchString(sdk) {
\t\tadd("sdk_range", "sdk", "sdk is a caret range like ^0.3.")
\t}
\t_, hasEntry := data["entry"]
\t_, hasPage := data["page"]
\tif !hasEntry && !hasPage {
\t\tadd("manifest_entry", "entry", "The app needs an entry (its Python file) or a page.")
\t}
\tif hasEntry && !relativeFile(data["entry"], ".py") {
\t\tadd("manifest_entry", "entry", "entry is a .py file inside the app.")
\t}
\tif hasPage && !relativeFile(data["page"], ".html") {
\t\tadd("manifest_page", "page", "page is an .html file inside the app.")
\t}
\tif value, present := data["permissions"]; present {
\t\tpermissions, ok := value.(map[string]any)
\t\tif !ok {
\t\t\tadd("permission_reason", "permissions", "permissions is an object of code to reason.")
\t\t}
\t\tfor code, reason := range permissions {
\t\t\tparam := "permissions." + code
\t\t\tif !contains(PermissionCodes, code) {
\t\t\t\tadd("permission_unknown", param, code+" is not a permission.")
\t\t\t\tcontinue
\t\t\t}
\t\t\tif code == "network" {
\t\t\t\tnetwork, ok := reason.(map[string]any)
\t\t\t\tif !ok {
\t\t\t\t\tadd("network_hosts", param, "network says why, and which hosts.")
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\thosts, _ := network["hosts"].([]any)
\t\t\t\tif len(hosts) == 0 || len(hosts) > hostsMax || !allHosts(hosts) {
\t\t\t\t\tadd("network_hosts", param+".hosts", "hosts lists the domains the app reaches. The whole web, IPs and localhost are refused.")
\t\t\t\t}
\t\t\t\treason, param = network["why"], param+".why"
\t\t\t}
\t\t\ttext, ok := reason.(string)
\t\t\tif !ok || len([]rune(strings.TrimSpace(text))) < reasonMin || len([]rune(text)) > reasonMax {
\t\t\t\tadd("permission_reason", param, fmt.Sprintf("Each permission has a reason the person reads: one sentence, %%d to %%d characters.", reasonMin, reasonMax))
\t\t\t}
\t\t}
\t}
\tif value, present := data["accent"]; present {
\t\tif accent, ok := value.(string); !ok || !accentPattern.MatchString(accent) {
\t\t\tadd("manifest_accent", "accent", "accent is a colour like #5b8cff.")
\t\t}
\t}
\tif value, present := data["icon"]; present {
\t\ticon, ok := value.(string)
\t\tlower := strings.ToLower(icon)
\t\tif !ok || !(strings.HasSuffix(lower, ".svg") || strings.HasSuffix(lower, ".png")) || !relativeFile(icon, "") {
\t\t\tadd("manifest_icon", "icon", "icon is a square .svg or .png inside the app.")
\t\t}
\t}
\tif value, present := data["window"]; present {
\t\twindow, ok := value.(map[string]any)
\t\tif !ok || len(window) == 0 {
\t\t\tadd("manifest_window", "window", "window is an object of sizes in pixels.")
\t\t}
\t\tfor key, size := range window {
\t\t\tbounds, known := windowBounds[key]
\t\t\tnumber, isNumber := size.(float64)
\t\t\tif !known || !isNumber || number != float64(int(number)) || int(number) < bounds[0] || int(number) > bounds[1] {
\t\t\t\tadd("manifest_window", "window."+key, "window sizes are whole pixels within the allowed range.")
\t\t\t}
\t\t}
\t}
\tif value, present := data["tags"]; present {
\t\ttags, ok := value.([]any)
\t\tif !ok || len(tags) > tagsMax || !allWords(tags) {
\t\t\tadd("manifest_tags", "tags", fmt.Sprintf("tags is up to %%d single words.", tagsMax))
\t\t}
\t}
\treturn found
}

func relativeFile(value any, suffix string) bool {
\tpath, ok := value.(string)
\tif !ok || path == "" || len(path) > 200 || strings.HasPrefix(path, "/") || strings.Contains(path, "\\\\") || !strings.HasSuffix(path, suffix) {
\t\treturn false
\t}
\tfor _, part := range strings.Split(path, "/") {
\t\tif part == ".." {
\t\t\treturn false
\t\t}
\t}
\treturn true
}

func allHosts(hosts []any) bool {
\tfor _, value := range hosts {
\t\thost, ok := value.(string)
\t\tif !ok || len(host) > hostMax || host == "localhost" || net.ParseIP(host) != nil || !hostPattern.MatchString(host) {
\t\t\treturn false
\t\t}
\t}
\treturn true
}

func allWords(tags []any) bool {
\tfor _, value := range tags {
\t\ttag, ok := value.(string)
\t\tif !ok || tag == "" || len(tag) > 64 || strings.ContainsAny(tag, " \\t\\n") {
\t\t\treturn false
\t\t}
\t}
\treturn true
}

func contains(list []string, value string) bool {
\tfor _, item := range list {
\t\tif item == value {
\t\t\treturn true
\t\t}
\t}
\treturn false
}
"""


def go(c: dict) -> str:
    r = rules(c)
    host = r["HOST_PATTERN"]
    host_len = 253
    lookahead = re.match(r"\^\(\?=\.\{1,(\d+)\}\$\)", host)
    if lookahead:  # RE2 has no lookahead: check the length in code instead
        host_len = int(lookahead.group(1))
        host = "^" + host[lookahead.end():]
    quote = lambda text: "`" + text + "`"  # noqa: E731
    strings = lambda items: "[]string{" + ", ".join(json.dumps(item) for item in items) + "}"  # noqa: E731
    fixes = ", ".join(f"{json.dumps(code)}: {json.dumps(info['fix'], ensure_ascii=False)}" for code, info in r["ERRORS"].items() if info["area"] == "check")
    return GO_TEMPLATE % {
        "schema": json.dumps(r["SCHEMA"]), "fields": strings(r["FIELDS"]), "codes": strings(r["PERMISSIONS"]),
        "name": quote(r["NAME_PATTERN"]), "version": quote(r["VERSION_PATTERN"]), "sdk": quote(r["SDK_PATTERN"]),
        "accent": quote(r["ACCENT_PATTERN"]), "license": quote(r["LICENSE_PATTERN"]), "host": quote(host),
        "name_min": r["NAME_LENGTH"][0], "name_max": r["NAME_LENGTH"][1], "display": r["DISPLAY_NAME_MAX"], "summary": r["SUMMARY_MAX"],
        "reason_min": r["REASON_LENGTH"][0], "reason_max": r["REASON_LENGTH"][1], "hosts_max": r["HOSTS_MAX"], "host_len": host_len,
        "tags_max": r["TAGS_MAX"], "window": ", ".join(f"{json.dumps(k)}: {{{v[0]}, {v[1]}}}" for k, v in r["WINDOW"].items()),
        "fixes": fixes,
    }


# --- the design system, for the MCP ui_components tool -------------------------------------------


def _exports(ds: Path) -> dict[str, Path]:
    """What @0x1audio/design-system exports, and the file each name comes from (src/index.ts)."""
    import re

    found: dict[str, Path] = {}
    index = (ds / "src" / "index.ts").read_text()
    for names, module in re.findall(r"export\s*\{([^}]*)\}\s*from\s*\"(\./[^\"]+)\"", index):
        file = next((ds / "src" / (module[2:] + suffix) for suffix in (".tsx", ".ts") if (ds / "src" / (module[2:] + suffix)).is_file()), None)
        if file is None:
            continue
        for name in names.split(","):
            name = name.strip()
            if name and not name.startswith("type "):
                found[name.split(" as ")[-1].strip()] = file
    return found


def _helper(source: str, name: str) -> str:
    """`waveformFrom(source: Blob | Uint8Array, bars = 120): Promise<Wave>` from an exported function."""
    import re

    found = re.search(rf"^export (?:async )?function {name}\(([^)]*)\)(?:\s*:\s*([^{{]+?))?\s*\{{", source, re.M)
    if not found:
        return ""
    params = re.sub(r"\s+", " ", found.group(1)).strip()
    result = (found.group(2) or "").strip()
    return f"{name}({params})" + (f": {result}" if result else "")


def _signature(source: str, name: str) -> str:
    """The props a component takes, from `export function Name({ a, b = 1, ...props }: Type)`.
    ``source`` is the file index.ts exports the name from: a private one of the same name elsewhere
    (library-player.tsx has its own Waveform) is not the API."""
    import re

    found = re.search(rf"^(?:export )?function {name}\(", source, re.M)
    if not found:
        return ""
    i, depth = found.end(), 1
    start = i
    while i < len(source) and depth:
        depth += {"(": 1, ")": -1}.get(source[i], 0)
        i += 1
    params = re.sub(r"//[^\n]*", "", source[start : i - 1]).strip()
    if not params.startswith("{"):
        return ""
    depth, j = 0, 0
    for j, char in enumerate(params):
        depth += {"{": 1, "}": -1}.get(char, 0)
        if depth == 0:
            break
    names = []
    for part in re.split(r",(?![^{(\[]*[})\]])", params[1:j]):
        part = part.strip()
        if part:
            names.append(part.split("=")[0].split(":")[0].strip())
    kind = re.sub(r"\s+", " ", params[j + 1 :].lstrip(":").strip())
    if kind.startswith("{"):  # an inline type: show each prop with its type, ? for optional
        raw = params[j + 1 :].lstrip(":").strip().strip("{}")
        space = re.compile(r"\s+")  # outside the f-string: Python 3.11 allows no backslash in one
        typed = [f"{m.group(1)}{m.group(2)}: {space.sub(' ', m.group(3)).strip()}" for m in re.finditer(r"(\w+)(\??)\s*:\s*([^\n;]+)", raw)]
        if typed and len(", ".join(typed)) <= 200:
            return ", ".join(typed)
    shown = ", ".join(name for name in names if name)
    return shown + (f" ({kind})" if kind and "{" not in kind and len(kind) <= 70 else "")


def _clip(text: str, limit: int) -> str:
    """At most ``limit`` characters, cut after a whole word, never inside one ("drawn as an outli")."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:—- ")
    return f"{cut}…"


def ui_index() -> dict | None:
    """Components an app page may use (DESIGN.md › Components, with their props) and the colour tokens."""
    import re

    ds = PROJECTS / "0x1audio-cloud" / "packages" / "design-system"
    design = ds / "DESIGN.md"
    if not design.is_file():
        return None
    text = design.read_text()
    section = text.split("## Components", 1)[1].split("\n## ", 1)[0]
    exports = _exports(ds)
    skip = {"Sidebar*", "LibraryPlayer", "LibraryBrowser", "Tile", "SettingsGroup", "SettingsRow", "LibraryUploadButton"}
    components = []
    group = ""
    for line in section.splitlines():
        if line.startswith("### "):
            group = line[4:].strip()
            continue
        found = re.match(r"- (\*\*`[^`]+`\*\*(?:, \*\*`[^`]+`\*\*)*)(?: / `[^`]+`)?: (.*)", line)
        if not found:
            continue
        names = re.findall(r"`([^`]+)`", found.group(1))
        use = re.sub(r"\*\*|`", "", found.group(2)).strip()
        use = use.split(". ")[0].rstrip(".") + "."
        for name in names:
            if name in skip or name not in exports:
                continue
            components.append({"name": name, "group": group, "props": _signature(exports[name].read_text(), name), "use": _clip(use, 160)})
    # Exported functions that go with the listed components (waveformFrom for Waveform), with their signatures.
    files = {exports[item["name"]] for item in components}
    helpers = []
    for name, file in sorted(exports.items()):
        if file in files and name[:1].islower():
            signature = _helper(file.read_text(), name)
            if signature:
                helpers.append(signature)
    # Exported interfaces the helpers and props name, like Wave.
    types = {}
    for file in sorted(files):
        for name, body in re.findall(r"^export interface (\w+) \{([^}]*)\}", file.read_text(), re.M):
            if "{" not in body and any(name in text for text in helpers + [item["props"] for item in components]):
                types[name] = "{ " + "; ".join(line.strip().rstrip(";,") for line in body.strip().splitlines() if line.strip() and not line.strip().startswith("//")) + " }"
    theme = (ds / "src" / "theme.css").read_text()
    colours = sorted(set(re.findall(r"--color-([a-z-]+)\s*:", theme)))
    return {
        "import": 'import { Button, ... } from "@0x1audio/design-system"',
        "rules": "Only these components and tokens below the hero; no hex colours; one filled Button per view; design empty, working, done and error states; check light and dark.",
        "components": components,
        "helpers": helpers,
        "types": types,
        "tokens": {"colour": colours, "use_as": "bg-<token>, text-<token>, border-<token>"},
    }


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
    editor = PROJECTS / "0x1audio-cloud" / "apps" / "desktop" / "schema" / "app.schema.json"
    if editor.parent.is_dir():
        found[editor] = json.dumps(c["schema"], indent=2, ensure_ascii=False) + "\n"
    found[HERE / "dist" / "go" / "appmanifest" / "manifest.gen.go"] = go(c)
    # packages/design-system/src/contract.gen.ts is the Design pod's to copy in; --check compares it (see watched()).
    found[HERE / "dist" / "design-system" / "contract.gen.ts"] = typescript(c, "Design system copy: ActionForm's types.")
    index = ui_index()
    if index is not None:
        found[pkg / "docs" / "ui.json"] = json.dumps(index, indent=1, ensure_ascii=False) + "\n"
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
    agents_tokens, how = tokens(found.get(ROOT / "src" / "ox1audio" / "AGENTS.md", ""))
    if agents_tokens > AGENTS_BUDGET:
        issues.append(f"AGENTS.md is {agents_tokens} tokens ({how}), over its {AGENTS_BUDGET} budget.")
    llms_tokens, how = tokens(found.get(ROOT / "src" / "ox1audio" / "docs" / "llms.txt", ""))
    if llms_tokens > LLMS_BUDGET:
        issues.append(f"llms.txt is {llms_tokens} tokens ({how}), over its {LLMS_BUDGET} budget.")
    return issues


def watched() -> list[str]:
    """Copies other pods keep in their own folders: checked, never written from here."""
    issues = []
    design = PROJECTS / "0x1audio-cloud" / "packages" / "design-system" / "src" / "contract.gen.ts"
    source = HERE / "dist" / "design-system" / "contract.gen.ts"
    if design.is_file() and source.is_file() and design.read_text() != source.read_text():
        issues.append(f"{design} differs from {source}. Design pod: copy it over (cp {source} {design}).")
    return issues


def main(argv: list[str]) -> int:
    found = outputs()
    issues = problems(found)
    if "--only" in argv:
        # e.g. --only desktop: just the files another repo's tests care about.
        part = argv[argv.index("--only") + 1]
        found = {path: text for path, text in found.items() if part in str(path)}
    if "--check" in argv:
        drift = [path for path, text in found.items() if not path.is_file() or path.read_text() != text]
        for path in drift:
            issues.append(f"{path} is out of date. Run: python contract/generate.py")
        if "--only" not in argv or "design-system" in argv[argv.index("--only") + 1]:
            issues += watched()
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
