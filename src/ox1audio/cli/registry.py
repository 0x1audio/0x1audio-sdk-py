"""mixel login, publish and status: the reviewed registry, from the terminal.

The API (GAB-56):
    POST /api/v1/cli/login                  -> {device_code, user_code, verification_url, interval, expires_in}
    POST /api/v1/cli/login/poll {device_code} -> {token, account: {email}} or error authorization_pending / slow_down / expired_token
    POST /api/v1/registry/submissions {repository, commit, message?} -> {id, app, version, status, url}
    GET  /api/v1/registry/submissions?app=NAME -> {submissions: [{id, version, status, created, checks[], notes[]}]}
Errors are {error: {code, message, param?, doc_url?}}.

The token lives in ``~/.config/mixel/credentials.json`` (readable only by you), or comes from
``MIXEL_TOKEN``. ``MIXEL_API`` points the CLI at another Mixel cloud.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from ox1audio import __version__
from ox1audio.cli import check, out
from ox1audio.cli.out import AUTH, FAILED, NETWORK, OK, Stop

DEFAULT_API = "https://cloud.0x1audio.com"


def api() -> str:
    return (os.environ.get("MIXEL_API") or DEFAULT_API).rstrip("/")


def credentials_file() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "mixel" / "credentials.json"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mixel" / "credentials.json"


def token() -> str | None:
    if os.environ.get("MIXEL_TOKEN"):
        return os.environ["MIXEL_TOKEN"]
    try:
        data = json.loads(credentials_file().read_text())
    except (OSError, ValueError):
        return None
    if data.get("api") not in (None, api()):
        return None
    return data.get("token") or None


def call(method: str, path: str, body: dict | None = None, *, signed: bool = True, what: str = "the registry") -> tuple[int, dict]:
    headers = {"content-type": "application/json", "user-agent": f"mixel/{__version__}", "accept": "application/json"}
    if signed:
        current = token()
        if not current:
            raise Stop("You're not signed in.", fix="mixel login", doc="publish#sign-in", code=AUTH, error="not_signed_in")
        headers["authorization"] = f"Bearer {current}"
    request = urllib.request.Request(api() + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read() or b"{}")
        except ValueError:
            data = {}
        if error.code == 401 and signed:
            raise Stop("Your sign-in has expired or was revoked.", fix="mixel login", doc="publish#sign-in", code=AUTH, error="not_signed_in") from None
        if error.code == 404 and not data.get("error"):
            raise Stop(f"This Mixel cloud ({api()}) doesn't take {what} from the CLI yet.", fix="update the server, or set MIXEL_API to one that does", code=NETWORK, error="registry_unavailable") from None
        return error.code, data
    except (urllib.error.URLError, OSError, ValueError) as error:
        reason = getattr(error, "reason", error)
        raise Stop(f"Couldn't reach Mixel at {api()}: {reason}.", fix="check your connection (MIXEL_API sets another address)", code=NETWORK, error="network") from None


def problem(data: dict, fallback: str) -> Stop:
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    fix = error.get("fix") or (f"see {error['doc_url']}" if error.get("doc_url") else "")
    return Stop(error.get("message") or fallback, fix=fix, code=FAILED, error=error.get("code", "registry_error"))


# --- login ------------------------------------------------------------------------------------


CLIENT_MAX = 60  # bytes; the cloud keeps longer names as plain "mixel"


def client_name(host: str | None = None) -> str:
    """How Account › Command line names this token: "mixel 0.3.0 on studio-mac", so machines differ."""
    base = f"mixel {__version__}"
    if host is None:
        try:
            host = socket.gethostname()
        except OSError:
            host = ""
    host = "".join(ch for ch in host.split(".")[0] if ch.isprintable()).strip()
    room = CLIENT_MAX - len(f"{base} on ".encode())
    while host and len(host.encode()) > room:
        host = host[:-1].rstrip()
    return f"{base} on {host}" if host else base


def login(args: list[str]) -> int:
    as_json = "--json" in args
    interactive = sys.stdout.isatty() and "--non-interactive" not in args and not as_json
    status, data = call("POST", "/api/v1/cli/login", {"client": client_name()}, signed=False, what="sign-in")
    if status >= 400 or not data.get("device_code"):
        raise problem(data, "Mixel couldn't start a sign-in.")
    code, url = data["user_code"], data["verification_url"]
    link = f"{url}?code={code}" if "?" not in url else url
    if as_json or not interactive:
        if as_json:
            out.emit({"url": link, "code": code, "expires_in": data.get("expires_in", 600)})
        else:
            print(f"Open {link} and confirm the code {code}.", flush=True)
    else:
        print(f"Your pairing code is  {code}")
        opened = webbrowser.open(link)
        print(f"{'Opened' if opened else 'Open'} {link}. Confirm the code there.", flush=True)
    interval = max(1, int(data.get("interval", 3)))
    deadline = time.monotonic() + int(data.get("expires_in", 600))
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, answer = call("POST", "/api/v1/cli/login/poll", {"device_code": data["device_code"]}, signed=False, what="sign-in")
        if status < 400 and answer.get("token"):
            save(answer["token"], answer.get("account", {}))
            who = answer.get("account", {}).get("email", "your Mixel account")
            if as_json:
                out.emit({"ok": True, "account": answer.get("account", {})})
            else:
                print(f"Signed in as {who}. Token saved in {credentials_file()}.")
            return OK
        reason = (answer.get("error") or {}).get("code")
        if reason == "slow_down":
            interval += 2
        elif reason != "authorization_pending":
            raise problem(answer, "The sign-in didn't finish.")
    raise Stop("The pairing code expired before it was confirmed.", fix="mixel login", code=AUTH, error="expired_token")


def save(value: str, account: dict) -> None:
    file = credentials_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump({"api": api(), "token": value, "account": account}, handle)
    os.replace(temp, file)


def logout(args: list[str]) -> int:
    file = credentials_file()
    if file.exists():
        file.unlink()
        print("Signed out. The token is removed from this computer (revoke it in your Mixel account to end it everywhere).")
    else:
        print("You weren't signed in.")
    return OK


# --- publish ----------------------------------------------------------------------------------


def git(folder: Path, *args: str, strip: bool = True) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=folder, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise Stop("git isn't installed.", fix="install git, then commit and push the app", code=FAILED, error="git_missing") from None
    if done.returncode != 0:
        raise Stop(f"git {' '.join(args)} failed: {done.stderr.strip().splitlines()[-1] if done.stderr.strip() else done.returncode}", fix="the app's folder must be a git repository pushed to GitHub", doc="publish", code=FAILED, error="git_failed")
    return done.stdout.strip() if strip else done.stdout


def repository(url: str) -> str | None:
    found = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", url.strip())
    return f"github.com/{found.group(1)}/{found.group(2)}" if found else None


def where(folder: Path) -> dict:
    """What would be submitted: the GitHub repository and the pushed commit. Refuses anything else."""
    try:
        inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=folder, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise Stop("git isn't installed.", fix="install git, then commit and push the app", code=FAILED, error="git_missing") from None
    if inside.returncode != 0:
        raise Stop("This folder isn't a git repository yet. Reviewers read the app on GitHub.", fix='git init -b main && git add -A && git commit -m "First version", then push it to GitHub', doc="publish", code=FAILED, error="git_failed")
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=folder, capture_output=True, timeout=30).returncode != 0:
        raise Stop("Nothing is committed yet.", fix='git add -A && git commit -m "First version" && git push', doc="publish", code=FAILED, error="git_failed")
    root = Path(git(folder, "rev-parse", "--show-toplevel")).resolve()
    if root != folder.resolve():
        raise Stop("The app must be at the top of its git repository: Mixel reads app.json there.", fix=f"move the app to its own repository (it is in {root})", doc="publish", code=FAILED, error="not_repo_root")
    dirty = [line[3:] for line in git(folder, "status", "--porcelain", strip=False).splitlines() if line.strip()]
    if dirty:
        raise Stop(f"There are changes that aren't committed ({dirty[0]}{' and more' if len(dirty) > 1 else ''}).", fix='git add -A && git commit -m "…" && git push', doc="publish", code=FAILED, error="git_dirty")
    commit = git(folder, "rev-parse", "HEAD")
    if not git(folder, "remote"):
        raise Stop("The repository has no remote: reviewers read the code on GitHub.", fix="create a public GitHub repository, then git remote add origin https://github.com/you/app.git && git push -u origin main", doc="publish", code=FAILED, error="not_github")
    remotes = git(folder, "branch", "-r", "--contains", "HEAD")
    if not remotes:
        raise Stop(f"Commit {commit[:7]} isn't pushed. Reviewers read the code on GitHub.", fix="git push", doc="publish", code=FAILED, error="git_not_pushed")
    remote = remotes.split()[0].split("/")[0]
    url = git(folder, "remote", "get-url", remote)
    repo = repository(url)
    if repo is None:
        raise Stop(f"{url} isn't a GitHub repository.", fix="push the app to a public GitHub repository", doc="publish", code=FAILED, error="not_github")
    return {"repository": repo, "commit": commit, "branch": git(folder, "rev-parse", "--abbrev-ref", "HEAD")}


def publish(args: list[str]) -> int:
    as_json = "--json" in args
    dry = "--dry-run" in args
    message = args[args.index("--message") + 1] if "--message" in args and args.index("--message") + 1 < len(args) else None
    folder = Path.cwd()
    report = check.run(folder)
    if not dry and not report.ok(strict=True):
        if as_json:
            out.emit({"ok": False, "stage": "check", **report.json(strict=True)})
        else:
            check.show(report, strict=True)
            print("\nmixel publish needs mixel check --strict to pass: no errors, no warnings.")
        return FAILED
    if dry:
        return dry_run(folder, report, as_json)
    target = where(folder)
    data = report.data
    summary = {"app": data.get("name"), "version": data.get("version"), **target}
    status, answer = call("POST", "/api/v1/registry/submissions", {**target, **({"message": message} if message else {})}, what="submissions")
    if status >= 400:
        raise problem(answer, "The registry refused the submission.")
    if as_json:
        out.emit({"ok": True, **summary, "submission": answer})
    else:
        print(f"Checks     passed\nGit        {target['branch']} at {target['commit'][:7]}, pushed to {target['repository']}")
        print(f"Submitted  {data.get('name')} {data.get('version')} for review.")
        if answer.get("url"):
            print(f"Status     {answer['url']}   or   mixel status")
    return OK


def dry_run(folder: Path, report, as_json: bool) -> int:
    """Every gate publish passes, each with its fix, without sending anything."""
    data = report.data
    gates = []
    problems = report.errors + report.warnings
    gates.append({"gate": "check", "ok": not problems, "detail": "passed" if not problems else f"{out.count(len(report.errors), 'error')}, {out.count(len(report.warnings), 'warning')}", **({} if not problems else {"fix": "mixel check --strict shows each one with its fix"})})
    target: dict = {}
    try:
        target = where(folder)
        gates.append({"gate": "git", "ok": True, "detail": f"{target['branch']} at {target['commit'][:7]}, pushed to {target['repository']}"})
    except Stop as stop:
        gates.append({"gate": "git", "ok": False, "detail": stop.message, "fix": stop.fix, "code": stop.error})
    signed = bool(token())
    gates.append({"gate": "sign-in", "ok": signed, "detail": "signed in" if signed else "not signed in", **({} if signed else {"fix": "mixel login"})})
    ok = all(gate["ok"] for gate in gates)
    if as_json:
        out.emit({"ok": ok, "dry_run": True, "app": data.get("name"), "version": data.get("version"), **target, "gates": gates})
        return OK if ok else FAILED
    labels = {"check": "Checks", "git": "Git", "sign-in": "Sign-in"}
    for gate in gates:
        print(f"{labels[gate['gate']]:<10} {'' if gate['ok'] else out.color('no', 'error') + '  '}{gate['detail']}")
        if gate.get("fix"):
            print(f"{'':<10} fix:  {gate['fix']}")
    print(f"{'Version':<10} {data.get('version')}")
    print("Dry run: nothing was sent. " + ("Run mixel publish to submit it for review." if ok else "Fix what says no, then run it again."))
    return OK if ok else FAILED


def status(args: list[str]) -> int:
    as_json = "--json" in args
    from ox1audio.manifest import check as manifest

    name = manifest(Path.cwd()).data.get("name")
    if not isinstance(name, str):
        raise Stop("There is no app.json with a name here.", fix="run mixel status in the app's folder", code=FAILED, error="manifest_missing")
    code, answer = call("GET", f"/api/v1/registry/submissions?app={name}", what="review status")
    if code >= 400:
        raise problem(answer, "The registry couldn't show this app's reviews.")
    submissions = answer.get("submissions", [])
    if as_json:
        out.emit({"ok": True, "app": name, "submissions": submissions})
        return OK
    if not submissions:
        print(f"{name}\n  nothing submitted yet. mixel publish sends this version for review.")
        return OK
    print(name)
    for item in submissions[:10]:
        state = str(item.get("status", "")).replace("_", " ")
        checks = item.get("checks") or []
        failed = [check_item for check_item in checks if not check_item.get("ok", True)]
        verdict = f"registry checks {'passed' if not failed else 'failed: ' + ', '.join(str(c.get('name')) for c in failed)}" if checks else ""
        print(f"  {str(item.get('version', '')):<8} {state:<12} submitted {str(item.get('created', ''))[:16].replace('T', ' ')}   {verdict}".rstrip())
        for note in item.get("notes") or []:
            print(f"  note     \"{note.get('body', '')}\" ({note.get('author', 'reviewer')}, {str(note.get('created', ''))[:10]})")
    return OK
