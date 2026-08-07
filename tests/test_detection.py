"""Tests for one-time AirGradient Local API detection."""

from __future__ import annotations

import asyncio
from typing import cast

from aiohttp.hdrs import METH_GET
from aioresponses import CallbackResult, aioresponses
import pytest
from yarl import URL

from airgradient import (
    AirGradientClient,
    AirGradientConnectionError,
    AirGradientParseError,
    ApiVersion,
)
from tests import load_fixture
from tests.const import MOCK_HOST, MOCK_URL


async def test_detects_legacy_with_one_request(responses: aioresponses) -> None:
    """Test that the default probe selects legacy immediately."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    async with AirGradientClient(MOCK_HOST) as client:
        measures = await client.get_current_measures()

    assert client.api_version is ApiVersion.LEGACY
    assert measures.model == "I-9PSL"


async def test_detects_v1_after_bare_legacy_404(
    responses: aioresponses,
) -> None:
    """Test fallback from an absent legacy route to V1."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=404,
        body="Not found",
        headers={"Content-Type": "text/plain"},
    )
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        body=load_fixture("v1/measures_minimal.json"),
    )
    async with AirGradientClient(MOCK_HOST) as client:
        measures = await client.get_current_measures()

    assert client.api_version is ApiVersion.V1
    assert measures.model == "P-1PSG"


async def test_v1_hint_skips_legacy_probe(responses: aioresponses) -> None:
    """Test that a V1 hint changes initial probe order."""
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        body=load_fixture("v1/measures_minimal.json"),
    )
    async with AirGradientClient(MOCK_HOST, api_version=ApiVersion.V1) as client:
        await client.get_current_measures()

    assert client.api_version is ApiVersion.V1


async def test_stale_v1_hint_falls_back_to_legacy(
    responses: aioresponses,
) -> None:
    """Test correction of a stale V1 hint during initial detection."""
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        status=404,
        body="Not found",
        headers={"Content-Type": "text/plain"},
    )
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    async with AirGradientClient(MOCK_HOST, api_version=ApiVersion.V1) as client:
        await client.get_current_measures()

    assert client.api_version is ApiVersion.LEGACY


async def test_unknown_hint_probes_normally(responses: aioresponses) -> None:
    """Test that an unknown runtime hint is not pre-seeded."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    client = AirGradientClient(MOCK_HOST, api_version=cast("ApiVersion", 2))
    async with client:
        await client.get_current_measures()

    assert client.api_version is ApiVersion.LEGACY


async def test_concurrent_initial_calls_share_probe(
    responses: aioresponses,
) -> None:
    """Test that concurrent first calls share one detection response."""

    async def response_handler(_: str, **_kwargs: object) -> CallbackResult:
        await asyncio.sleep(0)
        return CallbackResult(body=load_fixture("current_measures.json"))

    responses.get(f"{MOCK_URL}/measures/current", callback=response_handler)
    async with AirGradientClient(MOCK_HOST) as client:
        first, second = await asyncio.gather(
            client.get_current_measures(),
            client.get_current_measures(),
        )

    assert first == second
    assert client.api_version is ApiVersion.LEGACY


async def test_parse_error_does_not_probe_alternate(
    responses: aioresponses,
) -> None:
    """Test that a successful malformed response ends detection."""
    responses.get(f"{MOCK_URL}/measures/current", body="{}")
    async with AirGradientClient(MOCK_HOST) as client:
        with pytest.raises(AirGradientParseError):
            await client.get_current_measures()
    assert client.api_version is None
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_non_404_does_not_probe_alternate(responses: aioresponses) -> None:
    """Test that a non-404 HTTP failure ends detection."""
    responses.get(f"{MOCK_URL}/measures/current", status=500, body="failed")
    async with AirGradientClient(MOCK_HOST) as client:
        with pytest.raises(AirGradientConnectionError):
            await client.get_current_measures()
    assert client.api_version is None
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_json_404_does_not_count_as_bare_route(
    responses: aioresponses,
) -> None:
    """Test that a JSON-intended 404 does not trigger route fallback."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=404,
        body="{}",
        headers={"Content-Type": "application/json"},
    )
    async with AirGradientClient(MOCK_HOST) as client:
        with pytest.raises(AirGradientConnectionError):
            await client.get_current_measures()
    assert client.api_version is None
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_selected_backend_does_not_change_after_404(
    responses: aioresponses,
) -> None:
    """Test that later route failures do not trigger re-detection."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    responses.get(f"{MOCK_URL}/measures/current", status=404, body="Not found")
    async with AirGradientClient(MOCK_HOST) as client:
        await client.get_current_measures()
        with pytest.raises(AirGradientConnectionError):
            await client.get_current_measures()

    assert client.api_version is ApiVersion.LEGACY
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_probe_result_retained_when_config_detects(
    responses: aioresponses,
) -> None:
    """Test that config-triggered detection retains the first measures result."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    responses.get(f"{MOCK_URL}/config", body=load_fixture("config.json"))
    async with AirGradientClient(MOCK_HOST) as client:
        await client.get_config()
        measures = await client.get_current_measures()

    assert measures.serial_number == "84fce612f5b8"


async def test_new_client_detects_route_migration(responses: aioresponses) -> None:
    """Test that a new client can select routes changed by firmware."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    async with AirGradientClient(MOCK_HOST) as legacy_client:
        await legacy_client.get_current_measures()

    responses.get(
        f"{MOCK_URL}/measures/current",
        status=404,
        body="Not found",
        headers={"Content-Type": "text/plain"},
    )
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        body=load_fixture("v1/measures_minimal.json"),
    )
    async with AirGradientClient(MOCK_HOST) as v1_client:
        await v1_client.get_current_measures()

    assert legacy_client.api_version is ApiVersion.LEGACY
    assert v1_client.api_version is ApiVersion.V1
