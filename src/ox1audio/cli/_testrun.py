"""Runs an app's unittest tests and writes what happened as JSON. ``mixel test`` starts it.

    python -m ox1audio.cli._testrun RESULT.json [-k NAME]

It runs in the app's folder with the app's Python, so ``import app`` and the app's own
packages work the way they do in Mixel.
"""

from __future__ import annotations

import io
import json
import sys
import time
import traceback
import unittest
from pathlib import Path


class Recorder(unittest.TextTestResult):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.passed: list[str] = []
        self.problems: list[dict] = []

    def addSuccess(self, test) -> None:  # noqa: N802 - unittest's name
        super().addSuccess(test)
        self.passed.append(test.id())

    def addFailure(self, test, err) -> None:  # noqa: N802
        super().addFailure(test, err)
        self.problems.append(_problem(test, err, "failed"))

    def addError(self, test, err) -> None:  # noqa: N802
        super().addError(test, err)
        self.problems.append(_problem(test, err, "error"))

    def addSubTest(self, test, subtest, err) -> None:  # noqa: N802
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.problems.append(_problem(subtest, err, "failed"))


def _problem(test, err, kind: str) -> dict:
    exc_type, exc, tb = err
    frames = [frame for frame in traceback.extract_tb(tb) if "unittest" not in Path(frame.filename).parts]
    where = ""
    for frame in frames:
        if Path(frame.filename).resolve().is_relative_to(Path.cwd()):
            where = f"{Path(frame.filename).resolve().relative_to(Path.cwd())}:{frame.lineno}"
    missing = exc.name if isinstance(exc, ModuleNotFoundError) else None
    if missing is None and exc_type is ImportError and "No module named" in str(exc):
        missing = str(exc).split("'")[1] if "'" in str(exc) else None
    text = "".join(traceback.format_exception_only(exc_type, exc)).strip()
    # A test module that couldn't import shows the real error in its message.
    if test.id().startswith("unittest.loader._FailedTest"):
        lines = [line for line in str(exc).splitlines() if line.strip()]
        text = lines[-1].strip() if lines else text
        found = [line for line in lines if "ModuleNotFoundError" in line]
        if found and "'" in found[-1]:
            missing = found[-1].split("'")[1]
    return {
        "name": test.id().replace("unittest.loader._FailedTest.", ""),
        "kind": kind,
        "where": where,
        "message": text[:500],
        **({"missing": missing.split(".")[0]} if missing else {}),
    }


def main(argv: list[str]) -> int:
    target = Path(argv[0])
    pattern = argv[argv.index("-k") + 1] if "-k" in argv else None
    sys.path.insert(0, str(Path.cwd()))
    loader = unittest.TestLoader()
    if pattern:
        loader.testNamePatterns = [pattern if "*" in pattern else f"*{pattern}*"]
    # tests/ as a package (tests/__init__.py), or a plain folder of test files.
    suite = loader.discover("tests", top_level_dir="." if Path("tests/__init__.py").is_file() else "tests")
    started = time.monotonic()
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, resultclass=Recorder)
    result = runner.run(suite)
    target.write_text(json.dumps({
        "passed": len(result.passed),
        "failed": result.problems,
        "skipped": len(result.skipped),
        "seconds": round(time.monotonic() - started, 2),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
