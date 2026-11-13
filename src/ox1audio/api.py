"""The Mixel cloud from a script, typed from openapi.json: ``from ox1audio.api import connect``.

    from ox1audio.api import connect
    from ox1audio.cloud.api.default import app_catalog, me

    cloud = connect()            # the token `mixel login` saved (or MIXEL_TOKEN), on MIXEL_API or cloud.0x1audio.com
    print(me.sync(client=cloud).status)
    for app in app_catalog.sync(client=cloud).apps:
        print(app.display_name, app.version)

Every call returns its model or raises a ``MixelError`` (``ox1audio.errors``):

- ``MixelApiError`` when the cloud answered with an error status. It has the cloud's own ``code``
  (unauthenticated, waitlisted, authorization_pending, ...), plus ``status``, ``fix``, ``doc_url``
  and ``errors``, which lists every problem.
- ``MixelUnavailableError`` (code ``network``) when it can't be reached.
- ``MixelTimeoutError`` when it answers too slowly.

Each attempt may take ``timeout`` seconds (30). A GET is tried ``retries`` more times (2) after a
network failure, a timeout, or a 408, 429, 502, 503 or 504, honouring Retry-After up to 30 s. A POST
is never sent twice. The ``asyncio`` functions behave the same.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from email.utils import parsedate_to_datetime

import httpx

from ox1audio import __version__
from ox1audio.cloud import AuthenticatedClient, Client
from ox1audio.errors import (
    MixelApiError,
    MixelError,
    MixelTimeoutError,
    MixelUnavailableError,
)

__all__ = ["DEFAULT_CLOUD", "MixelApiError", "MixelError", "MixelTimeoutError", "MixelUnavailableError", "connect"]

DEFAULT_CLOUD = "https://cloud.0x1audio.com"
RETRY_STATUS = {408, 429, 502, 503, 504}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# Longer than this and the caller hears about the 429 instead of waiting it out.
LONGEST_WAIT = 30.0


def connect(token: str | None = None, *, base_url: str | None = None, timeout: float = 30.0, retries: int = 2) -> AuthenticatedClient | Client:
    """A client for the generated ``ox1audio.cloud.api`` functions, with timeouts, retries and typed errors.

    ``token`` defaults to MIXEL_TOKEN, or the token ``mixel login`` saved for this cloud. Without one,
    the client is signed out: health, cli_login and cli_login_poll still work.
    """
    from ox1audio.cli import registry

    where = (base_url or registry.api() or DEFAULT_CLOUD).rstrip("/")
    bearer = token if token is not None else registry.token()
    headers = {"user-agent": f"ox1audio/{__version__}", "accept": "application/json"}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    tries = max(0, int(retries))
    limit = httpx.Timeout(timeout)
    client: AuthenticatedClient | Client = AuthenticatedClient(base_url=where, token=bearer) if bearer else Client(base_url=where)
    client.set_httpx_client(httpx.Client(base_url=where, headers=headers, timeout=limit, transport=_Resilient(tries, where, timeout)))
    client.set_async_httpx_client(httpx.AsyncClient(base_url=where, headers=headers, timeout=limit, transport=_AsyncResilient(tries, where, timeout)))
    return client


def _backoff(attempt: int) -> float:
    """0.25–0.5 s, then 0.5–1 s, 1–2 s, … up to 8 s: spread out, so many clients don't retry in step."""
    return min(8.0, 0.5 * 2**attempt) * (0.5 + random.random() / 2)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def _wait(response: httpx.Response, attempt: int) -> float:
    found = _retry_after(response)
    return _backoff(attempt) if found is None else found


def _repeatable(request: httpx.Request) -> bool:
    return request.method in SAFE_METHODS or "idempotency-key" in request.headers


def _refusal(response: httpx.Response) -> MixelApiError:
    try:
        body = json.loads(response.content or b"{}")
    except ValueError:
        body = {}
    detail = body.get("error") if isinstance(body, dict) else None
    if not isinstance(detail, dict) or not isinstance(detail.get("code"), str):
        reason = f"{response.status_code} {response.reason_phrase}".strip()
        return MixelApiError(response.status_code, f"http_{response.status_code}", f"The Mixel cloud answered {reason}.")
    errors = [item for item in body.get("errors") or [] if isinstance(item, dict)]
    return MixelApiError(response.status_code, detail["code"], str(detail.get("message", "")), detail.get("fix"), param=detail.get("param"), doc_url=detail.get("doc_url"), errors=errors)


def _offline(where: str) -> MixelUnavailableError:
    return MixelUnavailableError("network", f"Couldn't reach the Mixel cloud at {where}.", "check the connection; MIXEL_API or base_url sets another address")


def _slow(where: str, seconds: float) -> MixelTimeoutError:
    return MixelTimeoutError(f"The Mixel cloud at {where} took longer than {seconds:g} s to answer.", "try again; a slow network may need a longer timeout")


class _Resilient(httpx.BaseTransport):
    def __init__(self, retries: int, where: str, seconds: float, inner: httpx.BaseTransport | None = None) -> None:
        self.retries, self.where, self.seconds = retries, where, seconds
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self.retries + 1):
            last = not _repeatable(request) or attempt >= self.retries
            try:
                response = self.inner.handle_request(request)
            except httpx.TimeoutException:
                if last:
                    raise _slow(self.where, self.seconds) from None
                time.sleep(_backoff(attempt))
                continue
            except httpx.TransportError:
                if last:
                    raise _offline(self.where) from None
                time.sleep(_backoff(attempt))
                continue
            wait = _wait(response, attempt)
            if not last and response.status_code in RETRY_STATUS and wait <= LONGEST_WAIT:
                response.close()
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                response.read()
                raise _refusal(response)
            return response
        raise AssertionError("unreachable")

    def close(self) -> None:
        self.inner.close()


class _AsyncResilient(httpx.AsyncBaseTransport):
    def __init__(self, retries: int, where: str, seconds: float, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.retries, self.where, self.seconds = retries, where, seconds
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        for attempt in range(self.retries + 1):
            last = not _repeatable(request) or attempt >= self.retries
            try:
                response = await self.inner.handle_async_request(request)
            except httpx.TimeoutException:
                if last:
                    raise _slow(self.where, self.seconds) from None
                await asyncio.sleep(_backoff(attempt))
                continue
            except httpx.TransportError:
                if last:
                    raise _offline(self.where) from None
                await asyncio.sleep(_backoff(attempt))
                continue
            wait = _wait(response, attempt)
            if not last and response.status_code in RETRY_STATUS and wait <= LONGEST_WAIT:
                await response.aclose()
                await asyncio.sleep(wait)
                continue
            if response.status_code >= 400:
                await response.aread()
                raise _refusal(response)
            return response
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        await self.inner.aclose()
