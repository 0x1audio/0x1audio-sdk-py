"""What mixel check refuses in an app's Python. It reads the code; it never runs it for this.

An app runs programs, opens raw sockets, runs code from strings or touches fixed paths only
by evading Mixel, so each of those is an error with its fix. Aliases (``import os as o``,
``e = eval``), ``getattr`` and ``importlib`` resolve to the name they stand for first, so
``getattr(__import__("o" + "s"), "system")`` is ``os.system``. Network use is not refused:
it makes the app need the ``network`` permission, with its hosts.
"""

from __future__ import annotations

import ast
import builtins as _builtins
import re
from dataclasses import dataclass, field
from pathlib import Path

from ox1audio.manifest import Finding

DOC = "actions#never"
PROGRAMS = "use ox.audio.convert, ox.audio.read or ox.audio.write instead of running programs"
NATIVE = "remove it; packages with native code come from pyproject.toml as wheels"
SOCKETS = 'remove it; use urllib.request, and declare "network": {"why": "…", "hosts": ["example.com"]} in app.json'
STRINGS = "call the function you mean directly; Mixel only runs code it can read"
PACKAGES = 'use urllib.request (the standard library), and declare "network": {"why": "…", "hosts": ["example.com"]} in app.json'
HOME = "use the files the person chooses (ox.Files, ox.Folder), ox.temp() or ox.data"
DYNAMIC = "import the module by name at the top of the file, so mixel check and the review can see it"

# Modules an app may not import at all, and the fix for each.
MODULES = {
    "subprocess": PROGRAMS, "_posixsubprocess": PROGRAMS, "pty": PROGRAMS, "pipes": PROGRAMS, "posix": PROGRAMS, "nt": PROGRAMS,
    "pexpect": PROGRAMS, "sh": PROGRAMS, "plumbum": PROGRAMS, "pydub": PROGRAMS, "ffmpeg": PROGRAMS,
    "webbrowser": "return the link in your result; a page can open https links",
    "ctypes": NATIVE, "_ctypes": NATIVE, "cffi": NATIVE,
    "socket": SOCKETS, "_socket": SOCKETS, "socketserver": SOCKETS, "asyncore": SOCKETS, "asynchat": SOCKETS,
    "http.server": "don't write a server: Mixel runs the actions", "xmlrpc.server": "don't write a server: Mixel runs the actions",
    "requests": PACKAGES, "httpx": PACKAGES, "aiohttp": PACKAGES, "urllib3": PACKAGES,
    "runpy": STRINGS, "code": STRINGS, "codeop": STRINGS, "marshal": STRINGS,
    "importlib.util": DYNAMIC, "importlib.machinery": DYNAMIC, "importlib.abc": DYNAMIC, "zipimport": DYNAMIC, "pkgutil": DYNAMIC,
}

# Names an app may not use, wherever they come from.
_os_programs = ["system", "popen", "fork", "forkpty", "posix_spawn", "posix_spawnp", "startfile",
                *(f"exec{s}" for s in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe")),
                *(f"spawn{s}" for s in ("l", "le", "lp", "lpe", "v", "ve", "vp", "vpe"))]
CALLS = {
    **{f"os.{name}": PROGRAMS for name in _os_programs},
    "asyncio.create_subprocess_exec": PROGRAMS, "asyncio.create_subprocess_shell": PROGRAMS, "asyncio.subprocess": PROGRAMS,
    "asyncio.open_connection": SOCKETS, "asyncio.start_server": SOCKETS, "asyncio.open_unix_connection": SOCKETS, "asyncio.start_unix_server": SOCKETS,
    "builtins.eval": STRINGS, "builtins.exec": STRINGS, "builtins.compile": STRINGS,
    "builtins.__import__": DYNAMIC, "importlib.import_module": DYNAMIC, "importlib.__import__": DYNAMIC,
}
# Methods that run programs or open sockets on whatever object has them (an asyncio loop).
METHODS = {"subprocess_exec": PROGRAMS, "subprocess_shell": PROGRAMS, "sock_connect": SOCKETS, "create_unix_connection": SOCKETS, "create_unix_server": SOCKETS, "create_datagram_endpoint": SOCKETS}
# Attributes that reach around the language: the classic ways out of any check.
DUNDERS = {"__builtins__", "__subclasses__", "__globals__", "__getattribute__", "f_globals", "f_builtins", "f_locals", "gi_frame", "tb_frame"}

# Network use: fine with the network permission and its hosts.
NETWORK = ("urllib.request", "http.client", "ftplib", "smtplib", "poplib", "imaplib", "nntplib", "telnetlib", "xmlrpc.client",
           "huggingface_hub", "torch.hub", "websocket", "websockets")

# SDK helpers that need a package the app must list itself (the SDK doesn't install numpy for every app).
NEEDS = {"ox1audio.audio.read": "numpy", "ox1audio.audio.write": "numpy"}

# Where a fixed path literal means a file outside the app: the first arguments of these.
_file_modules = {"os", "shutil", "pathlib", "glob", "io", "codecs", "tarfile", "zipfile", "sqlite3", "fileinput", "soundfile", "wave", "aifc", "numpy", "json", "tomllib"}
_home = {"os.path.expanduser", "pathlib.Path.home", "os.path.expandvars"}
_home_vars = {"HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME"}
_sensitive = {"os", "builtins", "subprocess", "importlib", "sys", "ctypes", "socket", "posix", "nt", "asyncio", "shutil", "io", "pathlib"}
_builtin_names = set(dir(_builtins))
_dynamic = {"builtins.__import__", "importlib.import_module", "importlib.__import__"}
_hostname = re.compile(r"https?://([A-Za-z0-9.-]+)")


@dataclass
class Scan:
    findings: list[Finding] = field(default_factory=list)
    # Where the code reaches the network, like "separate.py:18 (urllib.request)", and the hosts its URLs name.
    network: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    banned_imports: set[str] = field(default_factory=set)
    # Packages SDK helpers the code calls need, like numpy for ox.audio.read: package -> "app.py:3 (ox.audio.read)".
    needs: dict[str, str] = field(default_factory=dict)


def scan(folder: Path, skip: set[str], local: set[str] = frozenset()) -> Scan:  # type: ignore[assignment]
    """Every .py file in the app outside ``skip`` folders, plus native binaries it carries.
    ``local`` names the app's own modules: ``import code`` of its own code.py is fine."""
    import os

    found = Scan()
    paths = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name not in skip and name != ".git"]
        paths += [Path(root) / name for name in files]
    for path in sorted(paths):
        rel = path.relative_to(folder)
        if path.suffix.lower() in {".so", ".pyd", ".dylib", ".dll", ".exe"}:
            found.findings.append(Finding("banned_api", str(rel), f"{rel} is a compiled binary, which the review can't read.", NATIVE, DOC))
        elif path.suffix == ".py":
            scan_source(path.read_text(errors="replace"), str(rel), found, local)
    return found


def scan_source(text: str, rel: str, found: Scan | None = None, local: set[str] = frozenset()) -> Scan:  # type: ignore[assignment]
    found = found if found is not None else Scan()
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except SyntaxError:
        return found
    _Reader(rel, found, local).read(tree)
    return found


def _literal(node: ast.AST | None) -> str | None:
    """The string a node always is: "a", "a" + "b", f"a{'b'}", "".join(["a", "b"]), "ab"[::1]."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        parts = [_literal(value.value if isinstance(value, ast.FormattedValue) else value) for value in node.values]
        return "".join(parts) if all(part is not None for part in parts) else None  # type: ignore[arg-type]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join" and len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)):
        glue, parts = _literal(node.func.value), [_literal(item) for item in node.args[0].elts]
        return glue.join(parts) if glue is not None and all(part is not None for part in parts) else None  # type: ignore[arg-type]
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):  # "ssecorpbus"[::-1]
        base = _literal(node.value)
        bounds = [_int(part) for part in (node.slice.lower, node.slice.upper, node.slice.step)]
        if base is not None and all(bound is not False for bound in bounds):
            try:
                return base[slice(*bounds)]  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
    return None


def _int(node: ast.AST | None) -> int | None | bool:
    """A slice bound: None, a whole number, or False when it isn't fixed."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) is int:
        return -node.operand.value
    return False


def _prefix(node: ast.AST) -> str | None:
    """The fixed start of a string: "/etc/" in f"/etc/{name}" or "/etc/" + name."""
    whole = _literal(node)
    if whole is not None:
        return whole
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _prefix(node.left)
    if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
        return str(node.values[0].value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):  # Path("/etc") / "passwd"
        return _prefix(node.left)
    return None


def _outside(text: str) -> bool:
    if text in {"/dev/null", "nul", "NUL"}:
        return False
    return text.startswith(("/", "~", "\\\\")) or bool(re.match(r"[A-Za-z]:[\\/]", text))


def _covered(name: str, table) -> str | None:
    """The entry of ``table`` that ``name`` is, or is inside: "subprocess" for "subprocess.run"."""
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        key = ".".join(parts[:end])
        if key in table:
            return key
    return None


class _Reader:
    def __init__(self, rel: str, found: Scan, local: set[str]) -> None:
        self.rel = rel
        self.local = local
        self.found = found
        self.aliases: dict[str, str] = {"__builtins__": "builtins"}
        self.seen: set[str] = set()

    # --- what names stand for --------------------------------------------------------------

    def read(self, tree: ast.AST) -> None:
        # Built-in names always mean the built-in, even where a def or argument shadows them:
        # a shadow somewhere must not hide a real eval elsewhere in the file.
        nodes = list(ast.walk(tree))
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in self.local:
                        continue
                    self.aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    if alias.name != "*" and node.module.split(".")[0] not in self.local:
                        self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        # e = eval, run = os.system, o = __import__("os"): a name bound once to something we know.
        for _ in range(3):
            for node in nodes:
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    meaning = self.qual(node.value)
                    for target in targets:
                        if isinstance(target, ast.Name) and meaning:
                            self.aliases[target.id] = meaning
        # __import__("json") is the import of json: the function itself isn't refused there.
        self.calls_by_name = {id(node.func) for node in nodes if isinstance(node, ast.Call) and node.args and _literal(node.args[0]) is not None and self.qual(node.func) in _dynamic}
        for node in nodes:
            if id(node) not in self.calls_by_name:
                self.check(node)

    def qual(self, node: ast.AST | None) -> str | None:
        """The dotted name a node stands for, like "os.system", or None."""
        if isinstance(node, ast.Name):
            if node.id in self.aliases:
                return self.aliases[node.id]
            if node.id in _builtin_names:
                return f"builtins.{node.id}"
            return None
        if isinstance(node, ast.Attribute):
            base = self.qual(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Call):
            func = self.qual(node.func)
            first = _literal(node.args[0]) if node.args else None
            if func in _dynamic and first:
                return first
            if func == "builtins.getattr" and len(node.args) >= 2:
                base, attr = self.qual(node.args[0]), _literal(node.args[1])
                return f"{base}.{attr}" if base and attr else None
            if func == "builtins.globals":
                return "builtins.globals()"
            if func == "builtins.vars" and node.args:
                base = self.qual(node.args[0])
                return f"{base}.__dict__" if base else None
            return None
        if isinstance(node, ast.Subscript):
            key = _literal(node.slice)
            base = self.qual(node.value)
            if base and key:
                if base == "sys.modules":
                    return key
                if base == "builtins.globals()":
                    return self.aliases.get(key) or ("builtins" if key == "__builtins__" else None)
                if base.endswith(".__dict__"):
                    return f"{base[: -len('.__dict__')]}.{key}"
                if base == "builtins":  # __builtins__["eval"] when __builtins__ is a dict
                    return f"builtins.{key}"
            return None
        return None

    # --- what is refused -------------------------------------------------------------------

    def refuse(self, node: ast.AST, label: str, message: str, fix: str, code: str = "banned_api") -> None:
        key = f"{code}:{label}"
        if key in self.seen:
            return
        self.seen.add(key)
        where = f"{self.rel}:{getattr(node, 'lineno', 0)}"
        if code == "banned_api":
            self.found.findings.append(Finding("banned_api", where, message, fix, DOC))
        else:
            self.found.findings.append(Finding("path_outside", where, message, fix, DOC))

    def name(self, node: ast.AST, meaning: str) -> None:
        """A name the code uses, imported or reached: refuse it, or note network use."""
        module = _covered(meaning, MODULES)
        if module:
            self.found.banned_imports.add(module.split(".")[0])
            self.refuse(node, module, f"{module} is not allowed in apps.", MODULES[module])
            return
        call = _covered(meaning, CALLS)
        if call:
            shown = call.removeprefix("builtins.")
            self.refuse(node, shown, f"{shown} is not allowed in apps.", CALLS[call])
            return
        need = _covered(meaning, NEEDS)
        if need and NEEDS[need] not in self.found.needs:
            self.found.needs[NEEDS[need]] = f"{self.rel}:{getattr(node, 'lineno', 0)} ({need.replace('ox1audio.', 'ox.')})"
        net = _covered(meaning, NETWORK)
        if net and f"net:{net}" not in self.seen:
            self.seen.add(f"net:{net}")
            self.found.network.append(f"{self.rel}:{getattr(node, 'lineno', 0)} ({net})")

    def check(self, node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in self.local:
                    self.name(node, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] not in self.local:
            for alias in node.names:
                if alias.name == "*" and node.module in _sensitive:
                    self.refuse(node, f"from {node.module} import *", f"from {node.module} import * is not allowed in apps.", "import the names you use, one by one")
                self.name(node, node.module if alias.name == "*" else f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Attribute):
            if node.attr in DUNDERS:
                self.refuse(node, node.attr, f"{node.attr} is not allowed in apps: it reaches around the rules.", STRINGS)
            elif node.attr in METHODS:
                self.refuse(node, node.attr, f"{node.attr} is not allowed in apps.", METHODS[node.attr])
            elif isinstance(node.ctx, ast.Load):
                meaning = self.qual(node)
                if meaning:
                    self.name(node, meaning)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id == "__builtins__":
                self.refuse(node, "__builtins__", "__builtins__ is not allowed in apps: it reaches around the rules.", STRINGS)
            else:
                meaning = self.qual(node)
                if meaning:
                    self.name(node, meaning)
        elif isinstance(node, ast.Subscript):
            meaning = self.qual(node)
            if meaning:
                self.name(node, meaning)
            elif self.qual(node.value) == "os.environ" and _literal(node.slice) in _home_vars:
                self.refuse(node, "home", f"{_literal(node.slice)} points at the person's folders, which apps can't touch.", HOME, "path_outside")
        elif isinstance(node, ast.Call):
            self.call(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for host in _hostname.findall(node.value):
                if host not in self.found.hosts and "." in host:
                    self.found.hosts.append(host.lower())

    def call(self, node: ast.Call) -> None:
        func = self.qual(node.func)
        if not func:
            return
        first = node.args[0] if node.args else None
        meaning = self.qual(node)
        if meaning and meaning != func:
            self.name(node, meaning)
        # Dynamic names: what they load or reach can't be read.
        if func in _dynamic and _literal(first) is None:
            self.refuse(node, func.removeprefix("builtins."), f"{func.removeprefix('builtins.')} with a name mixel check can't read is not allowed in apps.", DYNAMIC)
        if func == "builtins.getattr" and len(node.args) >= 2:
            base = self.qual(node.args[0])
            if base and base.split(".")[0] in _sensitive and _literal(node.args[1]) is None:
                self.refuse(node, f"getattr({base})", f"getattr on {base} with a name mixel check can't read is not allowed in apps.", "use the attribute by name, like os.path.join")
        if func in {"operator.attrgetter", "operator.methodcaller"} and _literal(first) is not None:
            attr = _literal(first) or ""
            if attr in _os_programs or attr in {"eval", "exec", "compile", "__import__"} or attr in DUNDERS:
                self.refuse(node, f"{func}({attr})", f"{func}(\"{attr}\") is not allowed in apps.", PROGRAMS if attr in _os_programs else STRINGS)
        # Fixed paths outside the app.
        if func in _home or func.endswith(".home") and func.startswith("pathlib."):
            self.refuse(node, "home", f"{func.split('.')[-1]}() reaches the person's home folder, which apps can't touch.", HOME, "path_outside")
            return
        if func in {"os.getenv", "os.environ.get"} and _literal(first) in _home_vars:
            self.refuse(node, "home", f"{_literal(first)} points at the person's folders, which apps can't touch.", HOME, "path_outside")
            return
        if func == "builtins.open" or func.split(".")[0] in _file_modules or func.startswith("ox1audio.audio."):
            for argument in [*node.args[:2], *(item.value for item in node.keywords if item.arg in {"file", "path", "src", "dst", "name", "fname", "filename"})]:
                text = _prefix(argument)
                if text is not None and _outside(text):
                    self.refuse(node, f"path:{text}", f"{self.rel} opens {text}, a fixed path outside the app. Mixel blocks it, and the review refuses it.", HOME, "path_outside")
                    break
