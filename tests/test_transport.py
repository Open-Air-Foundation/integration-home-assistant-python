"""Focused tests for AirGradient HTTP response handling."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

from airgradient import AirGradientClient, AirGradientConnectionError, ApiVersion
from tests.const import MOCK_HOST

if TYPE_CHECKING:
    from aiohttp import ClientSession


class FakeResponse:
    """Minimal aiohttp response double."""

    def __init__(self, body: str, *, delay: float = 0) -> None:
        """Initialize the response double."""
        self.body = body
        self.delay = delay
        self.status = 200
        self.headers: dict[str, str] = {}
        self.released = False

    async def text(self) -> str:
        """Return the body after an optional delay."""
        await asyncio.sleep(self.delay)
        return self.body

    def release(self) -> None:
        """Record response release."""
        self.released = True


class FakeSession:  # pylint: disable=too-few-public-methods
    """Minimal aiohttp session double."""

    def __init__(self, response: FakeResponse) -> None:
        """Initialize the session double."""
        self.response = response

    async def request(self, *_args: object, **_kwargs: object) -> FakeResponse:
        """Return the configured response."""
        return self.response


async def test_response_released_after_success() -> None:
    """Test that successful responses are released."""
    response = FakeResponse(
        '{"serialNumber":"serial","model":"P-1PSG","firmware":"1","boot":0}'
    )
    session = cast("ClientSession", FakeSession(response))
    client = AirGradientClient(MOCK_HOST, session=session, api_version=ApiVersion.V1)

    await client.get_current_measures()

    assert response.released


async def test_body_read_is_within_timeout_and_released() -> None:
    """Test body-read timeout coverage and release on failure."""
    response = FakeResponse("{}", delay=0.1)
    session = cast("ClientSession", FakeSession(response))
    client = AirGradientClient(
        MOCK_HOST,
        session=session,
        request_timeout=0.01,
        api_version=ApiVersion.V1,
    )

    with pytest.raises(AirGradientConnectionError):
        await client.get_current_measures()

    assert response.released
