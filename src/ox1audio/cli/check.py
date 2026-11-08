"""mixel check: the one gate. The same rules Mixel applies when it opens an app, and the registry on submit."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ox1audio.cli import _safety, out
from ox1audio.cli.out import FAILED, OK, Stop
from ox1audio.manifest import Finding, check as check_manifest


@dataclass
class Report:
    folder: Path
    data: dict
    findings: list[Finding] = field(default_factory=list)
    actions: list = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    # The hosts the code's URLs name, for the network permission --fix writes.
    hosts: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity != "error"]

    def ok(self, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)

    def json(self, strict: bool = False) -> dict:
        return {
            "ok": self.ok(strict),
            "app": self.data.get("name") or self.folder.name,
            "version": self.data.get("version"),
            "errors": [item.json() for item in self.errors][:20],
            "warnings": [item.json() for item in self.warnings][:20],
            "actions": [item.name for item in self.actions],
            **({"fixed": self.fixed} if self.fixed else {}),
        }


def command(args: list[str]) -> int:
    flags = {arg for arg in args if arg.startswith("--")}
    unknown = flags - {"--json", "--strict", "--fix"}
    if unknown:
        raise Stop(f"mixel check has no option {sorted(unknown)[0]}.", fix="mixel check [folder] [--fix] [--strict] [--json]")
    paths = [arg for arg in args if not arg.startswith("--")]
    folder = Path(paths[0]) if paths else Path.cwd()
    if not folder.is_dir():
        raise Stop(f"{folder} is not a folder.", fix="run mixel check inside the app's folder, or give its path")
    report = run(folder, fix="--fix" in flags)
    strict = "--strict" in flags
    if "--json" in flags:
        out.emit(report.json(strict))
    else:
        show(report, strict)
    return OK if report.ok(strict) else FAILED


def show(report: Report, strict: bool = False) -> None:
    data = report.data
    title = f"{data.get('name') or report.folder.name} {data.get('version') or ''}".strip()
    print(f"Checking {title} (sdk {data.get('sdk', 'missing')})\n")
    for line in report.fixed:
        print(f"Fixed  {line}")
    if report.fixed:
        print()
    out.findings(report.findings)
    errors, warnings = report.errors, report.warnings
    if errors or (strict and warnings):
        failing = errors + (warnings if strict else [])
        tail = f", {out.count(len(warnings), 'warning')}" if warnings and not strict else ""
        print(f"{out.count(len(failing), 'error' if not strict else 'problem')}{tail}. Fix {'them' if len(failing) > 1 else 'it'}, then run mixel check again.")
        return
    names = [item.name for item in report.actions]
    actions = f"{out.count(len(names), 'action')}: {', '.join(names)}" if names else "no actions"
    print(f"No errors{', ' + out.count(len(warnings), 'warning') if warnings else ''}. {actions}.")


def run(folder: Path, fix: bool = False) -> Report:
    """Check the app in ``folder``. With ``fix``, first add the permissions the code uses to app.json."""
    folder = folder.resolve()
    report = _run(folder)
    if fix:
        fixed = _fix(folder, report)
        if fixed:
            report = _run(folder)
            report.fixed = fixed
    return report


def _run(folder: Path) -> Report:
    manifest = check_manifest(folder)
    report = Report(folder, manifest.data, list(manifest.findings))
    data = manifest.data
    worker = data.get("worker")
    entry = data.get("entry") or (worker.get("entry") if isinstance(worker, dict) else None)
    safety = _safety.scan(folder, _skip, _local(folder))
    report.findings += safety.findings
    report.hosts = safety.hosts
    if safety.findings:
        # Code that runs programs or reaches around the rules is not run, not even to list its actions.
        report.findings += _imports(folder, safety.banned_imports)
        return report
    if isinstance(entry, str) and (folder / entry).is_file():
        loaded, problem = _load_in_app(folder, folder / entry)
        if problem:
            report.findings.append(problem)
        else:
            report.actions = loaded
            used = set()
            for item in loaded:
                used |= item.permissions()
            used |= _static_permissions(folder)
            if safety.network:
                used.add("network")
            report.findings += _imports(folder, safety.banned_imports)
            declared = manifest.permissions
            if data.get("$schema"):
                for code in sorted(used - declared):
                    if code == "network":
                        hosts = json.dumps(safety.hosts[:3] or ["example.com"])
                        report.findings.append(Finding(
                            "permission_undeclared", "app.json › permissions.network",
                            f"The code reaches the network ({safety.network[0]}), but app.json doesn't ask for it.",
                            f'add "network": {{"why": "Download the model once.", "hosts": {hosts}}} to permissions (or run mixel check --fix), then say why in your own words', "permissions",
                        ))
                        continue
                    report.findings.append(Finding(
                        "permission_undeclared", f"app.json › permissions.{code}",
                        f"The code uses {code} ({_why_used(code)}), but app.json doesn't ask for it.",
                        f'add "{code}": "{_reason(code)}" to permissions (or run mixel check --fix), then say why in your own words', "permissions",
                    ))
                permissions = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
                for code, reason in permissions.items():
                    reason = reason.get("why") if isinstance(reason, dict) else reason
                    if isinstance(reason, str) and reason.strip().upper().startswith("TODO"):
                        report.findings.append(Finding("permission_reason", f"app.json › permissions.{code}", f"The reason for {code} is still a TODO.", f'write it for the person, like "{_reason(code)}"; they read it before they install', "permissions", "warn"))
                for code in sorted(declared - used - {"network"}):
                    report.findings.append(Finding("permission_unused", f"app.json › permissions.{code}", f"app.json asks for {code}, but the code doesn't seem to use it.", "remove it, so people aren't asked for more than the app needs", "permissions"))
    return report


class Loaded:
    """An action as the app's own Python described it."""

    def __init__(self, spec: dict, permissions: list[str]) -> None:
        self.name = spec["name"]
        self._spec = spec
        self._permissions = set(permissions)

    def spec(self) -> dict:
        return self._spec

    def permissions(self) -> set[str]:
        return self._permissions


def _load_in_app(folder: Path, entry: Path):
    """Load the actions with the app's Python (its .venv, else mixel's), so its packages are there."""
    import subprocess

    from ox1audio.cli.testing import app_env, interpreter

    python = interpreter(folder)
    done = subprocess.run([python, "-m", "ox1audio.cli._describe", str(entry)], cwd=folder, env=app_env(python), capture_output=True, text=True, timeout=300)
    try:
        body = json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        tail = (done.stderr.strip().splitlines() or ["no output"])[-1]
        return [], Finding("app_failed_to_load", entry.name, f"{entry.name} couldn't be loaded: {tail}", "run python app.py to see the whole error", "actions#an-action")
    if "finding" in body:
        return [], Finding(**body["finding"])
    return [Loaded(item["spec"], item["permissions"]) for item in body["actions"]], None


def _todo(code: str) -> str:
    return f"TODO: say why the app needs {code}, in one sentence."


def _fix(folder: Path, report: Report) -> list[str]:
    """Add each permission the code uses (with a reason to rewrite) and each package it imports."""
    fixed = _fix_dependencies(folder, report)
    missing = [item.where.rsplit(".", 1)[-1] for item in report.findings if item.code == "permission_undeclared"]
    if not missing:
        return fixed
    path = folder / "app.json"
    data = json.loads(path.read_text())
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
    for code in missing:
        permissions[code] = {"why": _todo(code), "hosts": report.hosts[:10]} if code == "network" else _todo(code)
    data["permissions"] = permissions
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return fixed + [f"permissions.{code} added with a TODO reason: write it, people read it before they install" for code in missing]


def _fix_dependencies(folder: Path, report: Report) -> list[str]:
    names = []
    for item in report.findings:
        if item.code == "dependency_missing" and item.severity == "error":
            found = re.search(r'add "([^"]+)" to pyproject', item.fix)
            if found and found.group(1) not in names:
                names.append(found.group(1))
    if not names:
        return []
    path = folder / "pyproject.toml"
    text = path.read_text() if path.is_file() else f'[project]\nname = "{folder.name}"\nversion = "0.1.0"\nrequires-python = ">=3.11"\ndependencies = []\n'
    match = re.search(r"(?ms)^\[project\].*?^dependencies\s*=\s*\[(.*?)\]", text)
    if not match:
        return []
    current = [part.strip() for part in match.group(1).split(",") if part.strip()]
    current += [f'"{name}"' for name in names]
    text = text[: match.start(1)] + ", ".join(current) + text[match.end(1):]
    path.write_text(text)
    return [f"pyproject.toml lists {name} now: install it with uv venv && uv pip install -r pyproject.toml" for name in names]


def _load(entry: Path):
    from ox1audio import app as runner
    from ox1audio.action import actions, clear

    clear()
    sys.path.insert(0, str(entry.parent))
    runner._loading = True
    try:
        spec = importlib.util.spec_from_file_location("__ox_check__", entry)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".")[0]
        if missing and _normal(_dist_names.get(missing, missing)) in _declared(entry.parent):
            return [], Finding("dependency_not_installed", entry.name, f"{missing} is in pyproject.toml but not installed, so the actions couldn't be checked.", "uv venv && uv pip install -r pyproject.toml   (mixel check, test and run use the app's .venv)", "actions#dependencies")
        return [], Finding("dependency_missing", f"{entry.name}{_line_of(exc, entry)}", f"{entry.name} imports {missing}, but pyproject.toml doesn't list it, so 0x1audio won't install it.", f'add "{_dist_names.get(missing, missing)}" to pyproject.toml › [project].dependencies', "actions#dependencies")
    except Exception as exc:  # noqa: BLE001 - every failure is reported as a finding
        text = str(exc)
        fix_line = re.search(r"\nfix:  (.*)", text)
        doc_line = re.search(r"\ndocs: https://docs\.0x1audio\.com/(\S+)", text)
        first = text.split("\nfix:")[0].strip() or type(exc).__name__
        return [], Finding("app_failed_to_load", f"{entry.name}{_line_of(exc, entry)}", f"{type(exc).__name__}: {first}", fix_line.group(1) if fix_line else "fix the error at that line", doc_line.group(1) if doc_line else "actions#an-action")
    finally:
        runner._loading = False
        sys.path.remove(str(entry.parent))
    found = actions()
    if not found:
        return [], Finding("no_actions", entry.name, f"{entry.name} has no actions.", '@ox.action("Title") above a function makes it an action', "actions#an-action")
    return found, None


def _line_of(exc: BaseException, entry: Path) -> str:
    tb = exc.__traceback__
    line = ""
    while tb is not None:
        if Path(tb.tb_frame.f_code.co_filename).resolve() == entry.resolve():
            line = f":{tb.tb_lineno}"
        tb = tb.tb_next
    return line


_library = re.compile(r"\b(ox\.)?(sound|midi|file)\(|\blibrary\.add\(")
_data = re.compile(r"\bdata\.(read|read_text|write|list|remove|root)\(|OX1_DATA")


def _static_permissions(folder: Path) -> set[str]:
    used: set[str] = set()
    for path in folder.rglob("*.py"):
        parts = set(path.relative_to(folder).parts)
        if parts & {".venv", "tests", "node_modules", "dist", "__pycache__"}:
            continue
        text = path.read_text(errors="replace")
        if _library.search(text) and "ox1audio" in text:
            used.add("library")
        if _data.search(text):
            used.add("data")
    return used


_skip = {".venv", "tests", "node_modules", "dist", "__pycache__"}


def _local(folder: Path) -> set[str]:
    # Anything that is a module or folder somewhere in the app counts as its own code (vendored trees add themselves to sys.path).
    return {path.stem for path in folder.rglob("*.py")} | {path.name for path in folder.rglob("*") if path.is_dir()}


def _imports(folder: Path, refused: set[str] = frozenset()) -> list[Finding]:  # type: ignore[assignment]
    """Python packages the code imports but pyproject.toml doesn't list (0x1audio installs only those).
    ``refused`` are packages mixel check already refuses (requests): never ask to add those."""
    import ast

    import warnings

    stdlib = set(sys.stdlib_module_names)
    local = _local(folder)
    declared = _declared(folder)
    found: list[Finding] = []
    seen: set[str] = set(refused)
    for path in sorted(folder.rglob("*.py")):
        rel = path.relative_to(folder)
        if set(rel.parts) & _skip:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        optional = {id(inner) for node in ast.walk(tree) if isinstance(node, ast.Try) for inner in ast.walk(node)}
        # `if TYPE_CHECKING:` imports never run.
        optional |= {id(inner) for node in ast.walk(tree) if isinstance(node, ast.If) and _type_checking(node.test) for inner in ast.walk(node)}
        # Imports inside functions, or in files below the app's own folder (vendored code), may never run: warn.
        lazy = {id(inner) for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for inner in ast.walk(node)}
        nested = len(rel.parts) > 1
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top in stdlib or top in local or top == "ox1audio" or top in seen or id(node) in optional:
                    continue
                if _normal(top) not in declared and _normal(_dist_names.get(top, top)) not in declared:
                    seen.add(top)
                    severity = "warn" if nested or id(node) in lazy else "error"
                    found.append(Finding("dependency_missing", f"{rel}:{node.lineno}", f"{rel} imports {top}, but pyproject.toml doesn't list it, so 0x1audio won't install it.", f'add "{_dist_names.get(top, top)}" to pyproject.toml › [project].dependencies', "actions#dependencies", severity))
    return found


def _type_checking(test) -> bool:
    import ast

    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


_dist_names = {"yaml": "pyyaml", "sklearn": "scikit-learn", "PIL": "pillow", "cv2": "opencv-python"}


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared(folder: Path) -> set[str]:
    path = folder / "pyproject.toml"
    if not path.is_file():
        return set()
    try:
        import tomllib

        data = tomllib.loads(path.read_text())
    except Exception:  # noqa: BLE001 - a broken pyproject is reported by the desktop's install
        return set()
    names = set()
    for spec in data.get("project", {}).get("dependencies", []) or []:
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(spec))
        if match:
            names.add(_normal(match.group(1)))
    requirements = folder / "requirements.txt"
    if requirements.is_file():
        for line in requirements.read_text().splitlines():
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if match and not line.strip().startswith("#"):
                names.add(_normal(match.group(1)))
    return names


def _why_used(code: str) -> str:
    return {"files": "a Files or Folder control", "library": "it returns or adds sounds", "data": "it uses ox.data"}.get(code, code)


def _reason(code: str) -> str:
    return {"files": "Open the songs you choose.", "library": "Save the results to your Library.", "data": "Remember your settings on this computer."}.get(code, "Why the app needs it.")
