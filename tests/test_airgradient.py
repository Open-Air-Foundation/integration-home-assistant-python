"""Tests for the client."""

from __future__ import annotations

import asyncio
from dataclasses import is_dataclass, replace
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import ClientError
from aiohttp.hdrs import METH_GET, METH_POST, METH_PUT
from aioresponses import CallbackResult, aioresponses
import pytest
from yarl import URL

from airgradient import (
    AirGradientBadRequestError,
    AirGradientBusyError,
    AirGradientClient,
    AirGradientConnectionError,
    AirGradientError,
    AirGradientForbiddenError,
    AirGradientHttpError,
    AirGradientInternalError,
    AirGradientNotSupportedError,
    AirGradientParseError,
    AltitudeUnit,
    ApiVersion,
    ConfigurationControl,
    CorrectionAlgorithm,
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


SERIAL_NUMBER = "84fce612f5b8"
GENERIC_FIRMWARE_URL = "https://api.airgradient.com/firmware/generic/current"
GO_FIRMWARE_URL = "https://api.airgradient.com/firmware/go/current"


def v1_client() -> AirGradientClient:
    """Create a V1-seeded client."""
    return AirGradientClient(MOCK_HOST, api_version=ApiVersion.V1)


def add_v1_probe(
    responses: aioresponses, fixture: str = "measures_minimal.json"
) -> None:
    """Add a successful V1 measures probe."""
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        body=load_fixture(f"v1/{fixture}"),
    )


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
        await airgradient.close()
        assert not session.closed


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
    session = airgradient.session
    assert session is not None
    assert not session.closed
    await airgradient.close()
    assert session.closed


def test_client_retains_dataclass_behavior() -> None:
    """Test compatibility with the previous dataclass client."""
    client = AirGradientClient(MOCK_HOST)
    replacement = replace(client, host="192.168.0.31")
    assert is_dataclass(client)
    assert replacement.host == "192.168.0.31"


async def test_detection_falls_back_to_v1(responses: aioresponses) -> None:
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
    async with AirGradientClient(MOCK_HOST) as airgradient:
        measures = await airgradient.get_current_measures()

    assert airgradient.api_version is ApiVersion.V1
    assert measures.model == "P-1PSG"


async def test_v1_hint_skips_legacy_probe(responses: aioresponses) -> None:
    """Test that a V1 hint changes initial probe order."""
    add_v1_probe(responses)
    async with v1_client() as airgradient:
        await airgradient.get_current_measures()

    assert airgradient.api_version is ApiVersion.V1
    assert (METH_GET, URL(f"{MOCK_URL}/measures/current")) not in responses.requests


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
    async with v1_client() as airgradient:
        await airgradient.get_current_measures()

    assert airgradient.api_version is ApiVersion.LEGACY


async def test_concurrent_initial_calls_share_probe(
    responses: aioresponses,
) -> None:
    """Test that concurrent first calls share one detection response."""

    async def response_handler(_: str, **_kwargs: object) -> CallbackResult:
        await asyncio.sleep(0)
        return CallbackResult(body=load_fixture("current_measures.json"))

    url = f"{MOCK_URL}/measures/current"
    responses.get(url, callback=response_handler)
    async with AirGradientClient(MOCK_HOST) as airgradient:
        first, second = await asyncio.gather(
            airgradient.get_current_measures(),
            airgradient.get_current_measures(),
        )

    assert first == second
    assert len(responses.requests[(METH_GET, URL(url))]) == 1


@pytest.mark.parametrize(
    ("status", "body", "headers", "error_type"),
    [
        (200, "{}", None, AirGradientParseError),
        (500, "failed", None, AirGradientConnectionError),
        (404, "{}", {"Content-Type": "application/json"}, AirGradientConnectionError),
    ],
)
async def test_detection_does_not_fallback_for_response_failures(
    responses: aioresponses,
    status: int,
    body: str,
    headers: dict[str, str] | None,
    error_type: type[AirGradientError],
) -> None:
    """Test failures other than a bare route 404 end detection."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        status=status,
        body=body,
        headers=headers,
    )
    async with AirGradientClient(MOCK_HOST) as airgradient:
        with pytest.raises(error_type):
            await airgradient.get_current_measures()

    assert airgradient.api_version is None
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_selected_api_is_sticky(responses: aioresponses) -> None:
    """Test that later route failures do not trigger re-detection."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    responses.get(f"{MOCK_URL}/measures/current", status=404, body="Not found")
    async with AirGradientClient(MOCK_HOST) as airgradient:
        await airgradient.get_current_measures()
        with pytest.raises(AirGradientConnectionError):
            await airgradient.get_current_measures()

    assert airgradient.api_version is ApiVersion.LEGACY
    assert (METH_GET, URL(f"{MOCK_URL}/api/v1/measures")) not in responses.requests


async def test_config_first_retains_probe(responses: aioresponses) -> None:
    """Test that config-triggered detection retains the measures result."""
    measures_url = f"{MOCK_URL}/measures/current"
    responses.get(measures_url, body=load_fixture("current_measures.json"))
    responses.get(f"{MOCK_URL}/config", body=load_fixture("config.json"))
    async with AirGradientClient(MOCK_HOST) as airgradient:
        await airgradient.get_config()
        measures = await airgradient.get_current_measures()

    assert measures.serial_number == SERIAL_NUMBER
    assert len(responses.requests[(METH_GET, URL(measures_url))]) == 1


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
        lambda client: client.set_altitude_unit(AltitudeUnit.METERS),
        lambda client: client.set_cloud_connection(True),
        lambda client: client.set_measurement_interval(30),
        lambda client: client.set_gps_mode(GpsMode.TRACKING),
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
    """Test that V1-only config is rejected by the legacy API."""
    responses.get(
        f"{MOCK_URL}/measures/current",
        body=load_fixture("current_measures.json"),
    )
    with pytest.raises(AirGradientNotSupportedError) as raised:
        await function(client)

    assert raised.value.status == 404
    assert raised.value.code == "not_found"
    assert (METH_PUT, URL(f"{MOCK_URL}/config")) not in responses.requests


@pytest.mark.parametrize(
    "fixture",
    ["measures_full.json", "measures_minimal.json", "measures_zero.json"],
)
async def test_v1_measures_fixtures(
    responses: aioresponses,
    snapshot: SnapshotAssertion,
    fixture: str,
) -> None:
    """Test normalized full, minimal, and zero-valued V1 measures."""
    add_v1_probe(responses, fixture)
    async with v1_client() as airgradient:
        assert await airgradient.get_current_measures() == snapshot
    assert airgradient.api_version is ApiVersion.V1


@pytest.mark.parametrize("missing", ["serialNumber", "model", "firmware", "boot"])
async def test_v1_measures_requires_identity(
    responses: aioresponses, missing: str
) -> None:
    """Test required V1 identity fields."""
    payload: dict[str, Any] = {
        "serialNumber": SERIAL_NUMBER,
        "model": "P-1PSG",
        "firmware": "1.0.0",
        "boot": 1,
    }
    del payload[missing]
    responses.get(f"{MOCK_URL}/api/v1/measures", payload=payload)
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientParseError):
            await airgradient.get_current_measures()


async def test_v1_measures_malformed_json(responses: aioresponses) -> None:
    """Test malformed successful V1 response handling."""
    responses.get(f"{MOCK_URL}/api/v1/measures", body="{")
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientParseError):
            await airgradient.get_current_measures()


async def test_v1_rejects_legacy_boot_count(responses: aioresponses) -> None:
    """Test that the legacy bootCount fallback is not used by V1."""
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        payload={
            "serialNumber": SERIAL_NUMBER,
            "model": "P-1PSG",
            "firmware": "1.0.0",
            "bootCount": 1,
        },
    )
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientParseError):
            await airgradient.get_current_measures()


@pytest.mark.parametrize("fixture", ["config_go.json", "config_partial.json"])
async def test_v1_config_fixtures(
    responses: aioresponses,
    snapshot: SnapshotAssertion,
    fixture: str,
) -> None:
    """Test normalized full and partial V1 config fixtures."""
    add_v1_probe(responses)
    responses.get(f"{MOCK_URL}/api/v1/config", body=load_fixture(f"v1/{fixture}"))
    async with v1_client() as airgradient:
        assert await airgradient.get_config() == snapshot


async def test_v1_config_preserves_zero_values(responses: aioresponses) -> None:
    """Test valid zero-valued V1 config fields."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={
            "measurementInterval": 1,
            "gpsMode": "off",
            "frontLedBrightness": 0,
            "backLedBrightness": 0,
            "touchLedIntensity": 0,
            "buzzerEnabled": False,
        },
    )
    async with v1_client() as airgradient:
        config = await airgradient.get_config()

    assert config.measurement_interval == 1
    assert config.gps_mode is GpsMode.OFF
    assert config.front_led_brightness == 0
    assert config.back_led_brightness == 0
    assert config.touch_led_intensity == 0
    assert config.buzzer_enabled is False


async def test_v1_config_rejects_invalid_altitude_unit(
    responses: aioresponses,
) -> None:
    """Test unsupported V1 altitude units fail config parsing."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={"altitudeUnit": "yards"},
    )
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientParseError):
            await airgradient.get_config()


async def test_v1_config_ignores_unknown_fields(responses: aioresponses) -> None:
    """Test forward-compatible additive config fields."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={"pmStandard": "ugm3", "futureField": "ignored"},
    )
    async with v1_client() as airgradient:
        config = await airgradient.get_config()

    assert config.pm_standard is PmStandard.UGM3


async def test_v1_additional_correction_algorithms(
    responses: aioresponses,
) -> None:
    """Test EPA and nullable correction variants not covered by fixtures."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={
            "corrections": {
                "pm25": {"correctionAlgorithm": "epa_2021", "slr": None},
                "temperature": {"correctionAlgorithm": "none", "slr": None},
                "humidity": {
                    "correctionAlgorithm": "custom",
                    "slr": {"intercept": 2.0, "scalingFactor": 0.9},
                },
            }
        },
    )
    async with v1_client() as airgradient:
        config = await airgradient.get_config()

    assert config.corrections is not None
    assert config.corrections.pm25 is not None
    assert config.corrections.pm25.correction_algorithm is CorrectionAlgorithm.EPA_2021
    assert config.corrections.pm25.slr is None
    assert config.corrections.temperature is not None
    assert (
        config.corrections.temperature.correction_algorithm is CorrectionAlgorithm.NONE
    )
    assert config.corrections.temperature.slr is None
    assert config.corrections.humidity is not None
    assert (
        config.corrections.humidity.correction_algorithm is CorrectionAlgorithm.CUSTOM
    )
    assert config.corrections.humidity.slr is not None
    assert config.corrections.humidity.slr.intercept == 2.0
    assert config.corrections.humidity.slr.scaling_factor == 0.9


@pytest.mark.parametrize(
    ("function", "expected_path", "expected_method", "expected_data", "status"),
    [
        (
            lambda airgradient: airgradient.set_altitude_unit(AltitudeUnit.METERS),
            "config",
            METH_PUT,
            {"altitudeUnit": "m"},
            202,
        ),
        (
            lambda airgradient: airgradient.set_temperature_unit(
                TemperatureUnit.FAHRENHEIT
            ),
            "config",
            METH_PUT,
            {"temperatureUnit": "f"},
            202,
        ),
        (
            lambda airgradient: airgradient.set_pm_standard(PmStandard.USAQI),
            "config",
            METH_PUT,
            {"pmStandard": "us-aqi"},
            202,
        ),
        (
            lambda airgradient: airgradient.set_configuration_control(
                ConfigurationControl.LOCAL
            ),
            "config",
            METH_PUT,
            {"configurationControl": "local"},
            202,
        ),
        (
            lambda airgradient: airgradient.set_led_bar_mode(LedBarMode.CO2),
            "config",
            METH_PUT,
            {"ledMode": "co2"},
            202,
        ),
        (
            lambda airgradient: airgradient.enable_sharing_data(enable=True),
            "config",
            METH_PUT,
            {"postDataToCloud": True},
            202,
        ),
        (
            lambda airgradient: airgradient.set_co2_automatic_baseline_calibration(8),
            "config",
            METH_PUT,
            {"co2AbcDays": 8},
            202,
        ),
        (
            lambda airgradient: airgradient.set_cloud_connection(False),
            "config",
            METH_PUT,
            {"cloudConnection": False},
            202,
        ),
        (
            lambda airgradient: airgradient.set_display_brightness(50),
            "config",
            METH_PUT,
            {"displayBrightness": 50},
            202,
        ),
        (
            lambda airgradient: airgradient.set_led_bar_brightness(50),
            "config",
            METH_PUT,
            {"ledBarBrightness": 50},
            202,
        ),
        (
            lambda airgradient: airgradient.set_nox_learning_offset(12),
            "config",
            METH_PUT,
            {"noxLearningOffset": 12},
            202,
        ),
        (
            lambda airgradient: airgradient.set_tvoc_learning_offset(12),
            "config",
            METH_PUT,
            {"tvocLearningOffset": 12},
            202,
        ),
        (
            lambda airgradient: airgradient.set_measurement_interval(30),
            "config",
            METH_PUT,
            {"measurementInterval": 30},
            202,
        ),
        (
            lambda airgradient: airgradient.set_gps_mode(GpsMode.ALWAYS),
            "config",
            METH_PUT,
            {"gpsMode": "always"},
            202,
        ),
        (
            lambda airgradient: airgradient.set_front_led_brightness(3),
            "config",
            METH_PUT,
            {"frontLedBrightness": 3},
            202,
        ),
        (
            lambda airgradient: airgradient.set_back_led_brightness(2),
            "config",
            METH_PUT,
            {"backLedBrightness": 2},
            202,
        ),
        (
            lambda airgradient: airgradient.set_touch_led_intensity(1),
            "config",
            METH_PUT,
            {"touchLedIntensity": 1},
            202,
        ),
        (
            lambda airgradient: airgradient.set_buzzer_enabled(False),
            "config",
            METH_PUT,
            {"buzzerEnabled": False},
            202,
        ),
        (
            lambda airgradient: airgradient.request_co2_calibration(),
            "actions/calibrate-co2",
            METH_POST,
            None,
            200,
        ),
        (
            lambda airgradient: airgradient.request_led_bar_test(),
            "actions/test-leds",
            METH_POST,
            None,
            200,
        ),
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
async def test_v1_operation_routing(
    responses: aioresponses,
    function: Callable[[AirGradientClient], Awaitable[None]],
    expected_path: str,
    expected_method: str,
    expected_data: dict[str, Any] | None,
    status: int,
) -> None:
    """Test exact V1 methods, paths, payloads, and success statuses."""
    add_v1_probe(responses)
    url = f"{MOCK_URL}/api/v1/{expected_path}"
    responses.add(url, method=expected_method, status=status, body="")
    async with v1_client() as airgradient:
        await function(airgradient)
    responses.assert_called_with(
        url,
        expected_method,
        headers=HEADERS,
        json=expected_data,
    )
    assert len(responses.requests[(expected_method, URL(url))]) == 1


@pytest.mark.parametrize(
    ("status", "code", "error_type"),
    [
        (400, "invalid_body", AirGradientBadRequestError),
        (400, "unknown_field", AirGradientBadRequestError),
        (400, "invalid_value", AirGradientBadRequestError),
        (403, "forbidden", AirGradientForbiddenError),
        (404, "not_found", AirGradientNotSupportedError),
        (503, "busy", AirGradientBusyError),
        (500, "internal", AirGradientInternalError),
    ],
)
async def test_v1_structured_errors(
    responses: aioresponses,
    status: int,
    code: str,
    error_type: type[AirGradientHttpError],
) -> None:
    """Test structured V1 errors and diagnostic attributes."""
    add_v1_probe(responses)
    body = (
        '{"error":{"code":"'
        f"{code}"
        '","field":"temperatureUnit","message":"rejected"}}'
    )
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=status,
        body=body,
        headers={"Content-Type": "application/json"},
    )
    async with v1_client() as airgradient:
        with pytest.raises(error_type) as raised:
            await airgradient.set_temperature_unit(TemperatureUnit.CELSIUS)

    error = raised.value
    assert error.status == status
    assert error.code == code
    assert error.field == "temperatureUnit"
    assert error.message == "rejected"
    assert error.content_type == "application/json"
    assert error.body == body


async def test_v1_structured_error_without_field(
    responses: aioresponses,
) -> None:
    """Test the optional structured error field."""
    add_v1_probe(responses)
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=503,
        body='{"error":{"code":"busy","message":"retry later"}}',
        headers={"Content-Type": "application/json"},
    )
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientBusyError) as raised:
            await airgradient.set_pm_standard(PmStandard.UGM3)

    assert raised.value.field is None


@pytest.mark.parametrize(
    ("status", "body", "content_type"),
    [
        (404, '{"error":{"code":3}}', "application/json"),
        (400, '{"message":"rejected"}', "application/json"),
        (404, "Not found", "text/plain"),
    ],
)
async def test_v1_unstructured_errors_fall_back_to_connection_error(
    responses: aioresponses,
    status: int,
    body: str,
    content_type: str,
) -> None:
    """Test invalid or absent V1 error envelopes remain generic failures."""
    add_v1_probe(responses)
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=status,
        body=body,
        headers={"Content-Type": content_type},
    )
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientConnectionError):
            await airgradient.set_pm_standard(PmStandard.UGM3)


async def test_v1_config_requires_accepted_status(
    responses: aioresponses,
) -> None:
    """Test that V1 config strictly requires 202."""
    add_v1_probe(responses)
    responses.put(f"{MOCK_URL}/api/v1/config", status=200, body="")
    async with v1_client() as airgradient:
        with pytest.raises(AirGradientConnectionError):
            await airgradient.set_pm_standard(PmStandard.UGM3)


async def test_latest_version(
    responses: aioresponses, client: AirGradientClient, snapshot: SnapshotAssertion
) -> None:
    """Test the legacy firmware version lookup without a model."""
    responses.get(
        GENERIC_FIRMWARE_URL,
        status=200,
        body=load_fixture("version.txt"),
    )
    assert snapshot == await client.get_latest_firmware_version()
    responses.assert_called_with(
        GENERIC_FIRMWARE_URL,
        headers=HEADERS,
        json=None,
    )


@pytest.mark.parametrize(
    ("model", "firmware_url"),
    [
        ("P-1PSG", GO_FIRMWARE_URL),
        ("P-1PSG-TEST", GO_FIRMWARE_URL),
        ("I-9PSL", GENERIC_FIRMWARE_URL),
        ("I-9PSL-DE", GENERIC_FIRMWARE_URL),
        ("O-1PPT", GENERIC_FIRMWARE_URL),
        ("O-1PST", GENERIC_FIRMWARE_URL),
        ("DIY-PRO-4.3", GENERIC_FIRMWARE_URL),
        ("ABC", GENERIC_FIRMWARE_URL),
        ("", GENERIC_FIRMWARE_URL),
        (None, GENERIC_FIRMWARE_URL),
    ],
)
async def test_latest_version_for_model(
    responses: aioresponses,
    client: AirGradientClient,
    model: str | None,
    firmware_url: str,
) -> None:
    """Test selecting the firmware version URL for a device model."""
    responses.get(
        firmware_url,
        status=200,
        body=load_fixture("version.txt"),
    )

    assert await client.get_latest_firmware_version(model=model) == "3.1.4"
    responses.assert_called_with(
        firmware_url,
        headers=HEADERS,
        json=None,
    )
    assert len(responses.requests[(METH_GET, URL(firmware_url))]) == 1


async def test_version_parse_error(
    responses: aioresponses,
    client: AirGradientClient,
) -> None:
    """Test version parse error."""
    responses.get(
        GENERIC_FIRMWARE_URL,
        status=200,
        body="   ",
    )
    with pytest.raises(AirGradientParseError):
        await client.get_latest_firmware_version()
