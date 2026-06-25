"""Tests for the client."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import ClientError
from aiohttp.hdrs import METH_PUT
from aioresponses import CallbackResult, aioresponses
import pytest

from airgradient import (
    AirGradientClient,
    AirGradientConnectionError,
    AirGradientError,
    AirGradientParseError,
    ConfigurationControl,
    LedBarMode,
    PmStandard,
    TemperatureUnit,
)
from tests import load_fixture
from tests.const import HEADERS, MOCK_HOST, MOCK_URL

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from syrupy import SnapshotAssertion


async def test_putting_in_own_session(
    responses: aioresponses,
) -> None:
    """Test putting in own session."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=200,
        body=load_fixture("current_measures.json"),
    )
    async with aiohttp.ClientSession() as session:
        airgradient = AirGradientClient(session=session, host=MOCK_HOST)
        await airgradient.get_current_measures()
        assert airgradient.session is not None
        assert not airgradient.session.closed
        await airgradient.close()
        assert not airgradient.session.closed


async def test_creating_own_session(
    responses: aioresponses,
) -> None:
    """Test creating own session."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=200,
        body=load_fixture("current_measures.json"),
    )
    airgradient = AirGradientClient(host=MOCK_HOST)
    await airgradient.get_current_measures()
    assert airgradient.session is not None
    assert not airgradient.session.closed
    await airgradient.close()
    assert airgradient.session.closed


async def test_unexpected_server_response(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test handling unexpected response."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=404,
        headers={"Content-Type": "plain/text"},
        body="Yes",
    )
    with pytest.raises(AirGradientError):
        await client.get_current_measures()


async def test_unexpected_server_json_response(
    client: AirGradientClient,
    responses: aioresponses,
) -> None:
    """Test handling unexpected response missing required fields."""

    async def response_handler(_: str, **_kwargs: Any) -> CallbackResult:
        """Response handler for this test."""
        return CallbackResult(payload={})

    responses.get(
        f"{MOCK_URL}/measures/current",
        callback=response_handler,
    )
    with pytest.raises(AirGradientParseError):
        await client.get_current_measures()

    responses.get(
        f"{MOCK_URL}/config",
        callback=response_handler,
    )
    with pytest.raises(AirGradientParseError):
        await client.get_config()


async def test_timeout(
    responses: aioresponses,
) -> None:
    """Test request timeout."""

    # Faking a timeout by sleeping
    async def response_handler(_: str, **_kwargs: Any) -> CallbackResult:
        """Response handler for this test."""
        await asyncio.sleep(2)
        return CallbackResult(body="Goodmorning!")

    responses.get(
        f"{MOCK_URL}/measures/current",
        callback=response_handler,
    )
    async with AirGradientClient(request_timeout=1, host=MOCK_HOST) as airgradient:
        with pytest.raises(AirGradientConnectionError):
            await airgradient.get_current_measures()


async def test_client_error(
    client: AirGradientClient,
    responses: aioresponses,
) -> None:
    """Test client error."""

    async def response_handler(_: str, **_kwargs: Any) -> CallbackResult:
        """Response handler for this test."""
        raise ClientError

    responses.get(
        f"{MOCK_URL}/measures/current",
        callback=response_handler,
    )
    with pytest.raises(AirGradientConnectionError):
        await client.get_current_measures()


@pytest.mark.parametrize(
    "fixture",
    [
        "current_measures.json",
        "current_measures_2.json",
        "measures_after_boot.json",
        "current_measures_zero.json",
    ],
)
async def test_current_fixtures(
    responses: aioresponses,
    client: AirGradientClient,
    snapshot: SnapshotAssertion,
    fixture: str,
) -> None:
    """Test status call."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=200,
        body=load_fixture(fixture),
    )
    assert await client.get_current_measures() == snapshot


async def test_config(
    responses: aioresponses,
    client: AirGradientClient,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config call."""
    responses.get(
        f"{MOCK_URL}/config",
        status=200,
        body=load_fixture("config.json"),
    )
    assert await client.get_config() == snapshot


@pytest.mark.parametrize(
    ("function", "expected_data"),
    [
        (
            lambda client: client.set_temperature_unit(TemperatureUnit.CELSIUS),
            {"temperatureUnit": "c"},
        ),
        (
            lambda client: client.set_pm_standard(PmStandard.UGM3),
            {"pmStandard": "ugm3"},
        ),
        (
            lambda client: client.set_configuration_control(ConfigurationControl.CLOUD),
            {"configurationControl": "cloud"},
        ),
        (
            lambda client: client.set_led_bar_mode(LedBarMode.CO2),
            {"ledBarMode": "co2"},
        ),
        (
            lambda client: client.request_co2_calibration(),
            {"co2CalibrationRequested": True},
        ),
        (
            lambda client: client.request_led_bar_test(),
            {"ledBarTestRequested": True},
        ),
        (
            lambda client: client.set_display_brightness(50),
            {"displayBrightness": 50},
        ),
        (
            lambda client: client.set_led_bar_brightness(50),
            {"ledBarBrightness": 50},
        ),
        (
            lambda client: client.enable_sharing_data(enable=True),
            {"postDataToAirGradient": True},
        ),
        (
            lambda client: client.set_co2_automatic_baseline_calibration(50),
            {"abcDays": 50},
        ),
        (
            lambda client: client.set_nox_learning_offset(50),
            {"noxLearningOffset": 50},
        ),
        (
            lambda client: client.set_tvoc_learning_offset(50),
            {"tvocLearningOffset": 50},
        ),
    ],
)
async def test_setting_config(
    responses: aioresponses,
    client: AirGradientClient,
    function: Callable[[AirGradientClient], Awaitable[None]],
    expected_data: dict[str, Any],
) -> None:
    """Test config call."""
    responses.put(
        f"{MOCK_URL}/config",
        status=200,
        body="Success",
        headers={"Content-Type": "plain/text"},
    )
    await function(client)
    responses.assert_called_once_with(
        f"{MOCK_URL}/config",
        METH_PUT,
        headers=HEADERS,
        json=expected_data,
    )


async def test_latest_version(
    responses: aioresponses, client: AirGradientClient, snapshot: SnapshotAssertion
) -> None:
    """Test getting latest firmware version."""
    responses.get(
        "http://hw.airgradient.com/sensors/airgradient/generic/os/firmware",
        status=200,
        body=load_fixture("version.json"),
    )
    assert snapshot == await client.get_latest_firmware_version("84fce612f5b8")
    responses.assert_called_with(
        "http://hw.airgradient.com/sensors/airgradient/generic/os/firmware",
        headers=HEADERS,
        json=None,
    )


async def test_version_parse_error(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test version parse error."""
    responses.get(
        "http://hw.airgradient.com/sensors/airgradient/generic/os/firmware",
        status=200,
        body="{}",
    )
    with pytest.raises(AirGradientParseError):
        await client.get_latest_firmware_version("84fce612f5b8")
