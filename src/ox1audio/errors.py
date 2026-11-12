"""The errors of the Mixel clients: ``ox1audio.local`` (the Mixel on this computer) and ``ox1audio.api`` (the cloud).

Every failure is a ``MixelError`` with a stable ``code``, a sentence for a person (``message``) and,
when there is one, the next step (``fix``). Catch the class, or branch on ``code``; never on the message.

    MixelError               Mixel or the cloud refused: bad_input, unknown_id, crates_off, ...
    ├ MixelApiError          the cloud answered with an error status: also status, param, doc_url, errors
    ├ MixelUnavailableError  nothing answered: Mixel is closed, a switch is off, or no network
    └ MixelTimeoutError      it answered too slowly, after the retries

``str(error)`` is one line, and ``error.to_dict()`` is ``{code, message, fix}``: small enough to hand to a model.
These are for scripts and tools. Inside an app's action, raise ``ox.Problem`` instead.
"""

from __future__ import annotations

__all__ = ["MixelApiError", "MixelError", "MixelTimeoutError", "MixelUnavailableError"]


class MixelError(Exception):
    def __init__(self, code: str, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix or None

    def __str__(self) -> str:
        return f"{self.message} (fix: {self.fix})" if self.fix else self.message

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.code!r}, {self.message!r}{f', {self.fix!r}' if self.fix else ''})"

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, **({"fix": self.fix} if self.fix else {})}


class MixelUnavailableError(MixelError):
    pass


class MixelTimeoutError(MixelError):
    def __init__(self, message: str, fix: str | None = None) -> None:
        super().__init__("timeout", message, fix)


class MixelApiError(MixelError):
    def __init__(self, status: int, code: str, message: str, fix: str | None = None, *, param: str | None = None, doc_url: str | None = None, errors: list[dict] | None = None) -> None:
        super().__init__(code, message, fix)
        self.status = status
        self.param = param
        self.doc_url = doc_url
        # Every problem, when the cloud found more than one (a submission's app.json).
        self.errors = errors or []

    def to_dict(self) -> dict:
        return {**super().to_dict(), "status": self.status, **({"param": self.param} if self.param else {}), **({"doc_url": self.doc_url} if self.doc_url else {})}
