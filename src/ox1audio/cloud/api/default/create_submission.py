from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error import Error
from ...models.problem import Problem
from ...models.submission_body import SubmissionBody
from ...models.submission_created import SubmissionCreated
from ...types import Response


def _get_kwargs(
    *,
    body: SubmissionBody,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/registry/submissions",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Error | Problem | SubmissionCreated | None:
    if response.status_code == 201:
        response_201 = SubmissionCreated.from_dict(response.json())

        return response_201

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = Error.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Error | Problem | SubmissionCreated]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SubmissionBody,
) -> Response[Error | Problem | SubmissionCreated]:
    """Submit an app for review by commit

     For mixel publish. Takes a CLI token or a session. The repository must be one of the author's public
    GitHub repositories and the commit must be on it. app.json is read at that commit and checked with
    the same rules as mixel check (every problem in errors[]); a summary is required; the name can't
    change after publishing; an app that lists Python packages must commit uv.lock. Ten submissions an
    hour per account.

    Args:
        body (SubmissionBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | Problem | SubmissionCreated]
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
    body: SubmissionBody,
) -> Error | Problem | SubmissionCreated | None:
    """Submit an app for review by commit

     For mixel publish. Takes a CLI token or a session. The repository must be one of the author's public
    GitHub repositories and the commit must be on it. app.json is read at that commit and checked with
    the same rules as mixel check (every problem in errors[]); a summary is required; the name can't
    change after publishing; an app that lists Python packages must commit uv.lock. Ten submissions an
    hour per account.

    Args:
        body (SubmissionBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | Problem | SubmissionCreated
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SubmissionBody,
) -> Response[Error | Problem | SubmissionCreated]:
    """Submit an app for review by commit

     For mixel publish. Takes a CLI token or a session. The repository must be one of the author's public
    GitHub repositories and the commit must be on it. app.json is read at that commit and checked with
    the same rules as mixel check (every problem in errors[]); a summary is required; the name can't
    change after publishing; an app that lists Python packages must commit uv.lock. Ten submissions an
    hour per account.

    Args:
        body (SubmissionBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Error | Problem | SubmissionCreated]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: SubmissionBody,
) -> Error | Problem | SubmissionCreated | None:
    """Submit an app for review by commit

     For mixel publish. Takes a CLI token or a session. The repository must be one of the author's public
    GitHub repositories and the commit must be on it. app.json is read at that commit and checked with
    the same rules as mixel check (every problem in errors[]); a summary is required; the name can't
    change after publishing; an app that lists Python packages must commit uv.lock. Ten submissions an
    hour per account.

    Args:
        body (SubmissionBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Error | Problem | SubmissionCreated
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
