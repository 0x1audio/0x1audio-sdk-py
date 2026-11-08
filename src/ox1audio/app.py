"""Load an app's entry file and serve its actions. Mixel runs ``python -m ox1audio app.py``."""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

from ox1audio import _protocol
from ox1audio.action import actions

_loading = False


def run() -> None:
    """Serve this file's actions. Optional: Mixel already does this when it opens the app."""
    if _loading:
        return
    _protocol.serve(actions())


def main(entry: str) -> int:
    global _loading
    path = Path(entry).resolve()
    if not path.is_file():
        _protocol.fatal(f"{entry} is missing.", "app.json › entry names a file that is not in the app.")
        return 1
    sys.path.insert(0, str(path.parent))
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    _loading = True
    try:
        spec = importlib.util.spec_from_file_location(path.stem if path.stem.isidentifier() else "app", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"{path.name} is not a Python file.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except BaseException as exc:  # noqa: BLE001 - anything that stops the app from loading is reported to the window
        traceback.print_exc(file=sys.stderr)
        _protocol.fatal(f"{path.name} could not start.", _explain(exc, path), stdout=real_stdout.buffer)
        return 1
    finally:
        _loading = False
    found = actions()
    if not found:
        _protocol.fatal(
            f"{path.name} has no actions.",
            '@ox.action("Title") above a function makes it an action. docs: https://docs.0x1audio.com/actions',
            stdout=real_stdout.buffer,
        )
        return 1
    _protocol.serve(found, stdout=real_stdout.buffer)
    return 0


def _explain(exc: BaseException, path: Path) -> str:
    tb = exc.__traceback__
    line = ""
    while tb is not None:
        if Path(tb.tb_frame.f_code.co_filename).resolve().parent == path.parent:
            line = f"{Path(tb.tb_frame.f_code.co_filename).name}:{tb.tb_lineno}"
        tb = tb.tb_next
    text = str(exc).strip() or type(exc).__name__
    head = f"{type(exc).__name__} at {line}" if line else type(exc).__name__
    return f"{head}: {text}"
