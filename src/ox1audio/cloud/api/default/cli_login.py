from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cli_device import CliDevice
from ...models.cli_login_body import CliLoginBody
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: CliLoginBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cli/login",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CliDevice | Problem | None:
    if response.status_code == 200:
        response_200 = CliDevice.from_dict(response.json())

        return response_200

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[CliDevice | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CliLoginBody,
) -> Response[CliDevice | Problem]:
    """Start a mixel sign-in (device flow)

     The CLI shows user_code and opens verification_url?code=…; the person confirms it on the website
    while signed in. RFC 8628 style.

    Args:
        body (CliLoginBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CliDevice | Problem]
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
    body: CliLoginBody,
) -> CliDevice | Problem | None:
    """Start a mixel sign-in (device flow)

     The CLI shows user_code and opens verification_url?code=…; the person confirms it on the website
    while signed in. RFC 8628 style.

    Args:
        body (CliLoginBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CliDevice | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CliLoginBody,
) -> Response[CliDevice | Problem]:
    """Start a mixel sign-in (device flow)

     The CLI shows user_code and opens verification_url?code=…; the person confirms it on the website
    while signed in. RFC 8628 style.

    Args:
        body (CliLoginBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CliDevice | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CliLoginBody,
) -> CliDevice | Problem | None:
    """Start a mixel sign-in (device flow)

     The CLI shows user_code and opens verification_url?code=…; the person confirms it on the website
    while signed in. RFC 8628 style.

    Args:
        body (CliLoginBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CliDevice | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
