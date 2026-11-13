from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cli_poll_body import CliPollBody
from ...models.cli_token import CliToken
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: CliPollBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cli/login/poll",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CliToken | Problem | None:
    if response.status_code == 200:
        response_200 = CliToken.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[CliToken | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CliPollBody,
) -> Response[CliToken | Problem]:
    """Ask whether the pairing code was confirmed

     400 with error.code authorization_pending (keep polling every interval seconds), slow_down (add 2
    s), expired_token, access_denied or terms_required (stop; terms_required: the account hasn't agreed
    to the Terms, and the message says to agree on the web first). 200 gives the CLI token once; it is
    sent as Authorization Bearer.

    Args:
        body (CliPollBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CliToken | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: CliPollBody,
) -> CliToken | Problem | None:
    """Ask whether the pairing code was confirmed

     400 with error.code authorization_pending (keep polling every interval seconds), slow_down (add 2
    s), expired_token, access_denied or terms_required (stop; terms_required: the account hasn't agreed
    to the Terms, and the message says to agree on the web first). 200 gives the CLI token once; it is
    sent as Authorization Bearer.

    Args:
        body (CliPollBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CliToken | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CliPollBody,
) -> Response[CliToken | Problem]:
    """Ask whether the pairing code was confirmed

     400 with error.code authorization_pending (keep polling every interval seconds), slow_down (add 2
    s), expired_token, access_denied or terms_required (stop; terms_required: the account hasn't agreed
    to the Terms, and the message says to agree on the web first). 200 gives the CLI token once; it is
    sent as Authorization Bearer.

    Args:
        body (CliPollBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CliToken | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CliPollBody,
) -> CliToken | Problem | None:
    """Ask whether the pairing code was confirmed

     400 with error.code authorization_pending (keep polling every interval seconds), slow_down (add 2
    s), expired_token, access_denied or terms_required (stop; terms_required: the account hasn't agreed
    to the Terms, and the message says to agree on the web first). 200 gives the CLI token once; it is
    sent as Authorization Bearer.

    Args:
        body (CliPollBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CliToken | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
