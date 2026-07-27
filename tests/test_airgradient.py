"""Tests for the client."""

from __future__ import annotations

import asyncio
from dataclasses import is_dataclass, replace
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import ClientError
from aiohttp.hdrs import METH_GET, METH_PUT
from aioresponses import CallbackResult, aioresponses
import pytest
from yarl import URL

from airgradient import (
    AirGradientClient,
    AirGradientConnectionError,
    AirGradientError,
    AirGradientNotSupportedError,
    AirGradientParseError,
    ApiVersion,
    ConfigurationControl,
    GpsMode,
    LedBarMode,
    Measures,
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
        async with AirGradientClient(session=session, host=MOCK_HOST) as airgradient:
            await airgradient.get_current_measures()
            assert airgradient.session is not None
            assert not airgradient.session.closed
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
    async with AirGradientClient(host=MOCK_HOST) as airgradient:
        await airgradient.get_current_measures()
        assert airgradient.session is not None
        assert not airgradient.session.closed
    assert airgradient.session is not None
    assert airgradient.session.closed


def test_client_retains_dataclass_behavior() -> None:
    """Test compatibility with the previous dataclass client."""
    client = AirGradientClient(MOCK_HOST)
    replacement = replace(client, host="192.168.0.31")
    assert is_dataclass(client)
    assert replacement.host == "192.168.0.31"


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
    responses.get(f"{MOCK_URL}/api/v1/measures", status=404, body="Not found")
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
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
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
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


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
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


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
    assert client.api_version is ApiVersion.LEGACY


async def test_legacy_boot_count_fallback(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test legacy bootCount fallback for older devices."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("legacy_boot_count_only.json"),
    )
    measures = await client.get_current_measures()
    assert measures.boot_time == 4


async def test_legacy_requires_boot_or_boot_count(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test that legacy measures require one uptime field."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        payload={
            "wifi": -52,
            "serialno": "84fce612f5b8",
            "firmware": "3.1.1",
            "model": "I-9PSL",
        },
    )
    with pytest.raises(AirGradientParseError):
        await client.get_current_measures()


def test_measures_retains_positional_identity_fields() -> None:
    """Test compatibility with the previous positional constructor order."""
    measures = Measures(None, "serial", 1, "firmware", "model")
    assert measures.signal_strength is None
    assert measures.serial_number == "serial"
    assert measures.boot_time == 1


async def test_config(
    responses: aioresponses,
    client: AirGradientClient,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config call."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=200,
        body=load_fixture("current_measures.json"),
    )
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
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=200,
        body=load_fixture("current_measures.json"),
    )
    await function(client)
    responses.assert_called_with(
        f"{MOCK_URL}/config",
        METH_PUT,
        headers=HEADERS,
        json=expected_data,
    )
    assert len(responses.requests[(METH_PUT, URL(f"{MOCK_URL}/config"))]) == 1


@pytest.mark.parametrize(
    "function",
    [
        lambda client: client.set_cloud_connection(True),
        lambda client: client.set_measurement_interval(30),
        lambda client: client.set_gps_mode(GpsMode.TRACKING),
        lambda client: client.set_gps_interval(15),
        lambda client: client.set_front_led_brightness(3),
        lambda client: client.set_back_led_brightness(2),
        lambda client: client.set_touch_led_intensity(1),
        lambda client: client.set_buzzer_enabled(True),
    ],
)
async def test_v1_config_not_supported_by_legacy(
    responses: aioresponses,
    client: AirGradientClient,
    function: Callable[[AirGradientClient], Awaitable[None]],
) -> None:
    """Test that V1-only config is rejected by the legacy backend."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    with pytest.raises(AirGradientNotSupportedError) as raised:
        await function(client)

    assert raised.value.status == 404
    assert raised.value.code == "not_found"
    assert (METH_PUT, URL(f"{MOCK_URL}/config")) not in responses.requests


async def test_latest_version(
    responses: aioresponses, client: AirGradientClient, snapshot: SnapshotAssertion
) -> None:
    """Test getting latest firmware version."""
    responses.get(
        "http://hw.airgradient.com/sensors/airgradient:84fce612f5b8/generic/os/firmware",
        status=200,
        body=load_fixture("version.json"),
    )
    assert snapshot == await client.get_latest_firmware_version("84fce612f5b8")
    responses.assert_called_with(
        "http://hw.airgradient.com/sensors/airgradient:84fce612f5b8/generic/os/firmware",
        headers=HEADERS,
        json=None,
    )


async def test_version_parse_error(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test version parse error."""
    responses.get(
        "http://hw.airgradient.com/sensors/airgradient:84fce612f5b8/generic/os/firmware",
        status=200,
        body="{}",
    )
    with pytest.raises(AirGradientParseError):
        await client.get_latest_firmware_version("84fce612f5b8")
