"""Tests for AirGradient Local API V1."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp.hdrs import METH_POST, METH_PUT
from aioresponses import aioresponses
import pytest
from yarl import URL

from airgradient import (
    AirGradientBadRequestError,
    AirGradientBusyError,
    AirGradientClient,
    AirGradientConnectionError,
    AirGradientForbiddenError,
    AirGradientHttpError,
    AirGradientInternalError,
    AirGradientNotSupportedError,
    AirGradientParseError,
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


async def get_v1_measures(responses: aioresponses, fixture: str) -> Measures:
    """Return V1 measures while checking behavior common to all payloads."""
    add_v1_probe(responses, fixture)
    async with v1_client() as client:
        measures = await client.get_current_measures()

    assert client.api_version is ApiVersion.V1
    assert measures.serial_number == "84fce612f5b8"
    assert measures.raw_pm02 is None
    assert measures.compensated_pm02 is None
    assert measures.raw_ambient_temperature is None
    assert measures.compensated_ambient_temperature is None
    assert measures.raw_relative_humidity is None
    assert measures.compensated_relative_humidity is None
    return measures


async def test_v1_full_measures(responses: aioresponses) -> None:
    """Test a V1 response with every optional measure."""
    measures = await get_v1_measures(responses, "measures_full.json")
    assert measures.boot_time == 42
    assert measures.firmware_version == "1.0.0"
    assert measures.signal_strength == -57
    assert measures.rco2 == 612
    assert measures.pm01 == 1.25
    assert measures.pm02 == 2.5
    assert measures.pm10 == 3.75
    assert measures.pm003_count == 100
    assert measures.pm005_count == 90
    assert measures.pm01_count == 80
    assert measures.pm02_count == 70
    assert measures.pm50_count == 60
    assert measures.pm10_count == 50
    assert measures.ambient_temperature == 21.5
    assert measures.relative_humidity == 48.25
    assert measures.total_volatile_organic_component_index == 101
    assert measures.raw_total_volatile_organic_component == 32100
    assert measures.nitrogen_index == 2
    assert measures.raw_nitrogen == 16000
    assert measures.battery_percentage == 87
    assert measures.battery_voltage == 3.91
    assert measures.charge_voltage == 5.02


async def test_v1_minimal_measures(responses: aioresponses) -> None:
    """Test a V1 response with no optional measures."""
    measures = await get_v1_measures(responses, "measures_minimal.json")
    assert measures.model == "P-1PSG"
    assert measures.firmware_version == "1.0.0"
    assert measures.boot_time == 0
    assert measures.signal_strength is None
    assert measures.rco2 is None
    assert measures.pm01 is None
    assert measures.pm02 is None
    assert measures.pm10 is None
    assert measures.pm003_count is None
    assert measures.pm005_count is None
    assert measures.pm01_count is None
    assert measures.pm02_count is None
    assert measures.pm50_count is None
    assert measures.pm10_count is None
    assert measures.ambient_temperature is None
    assert measures.relative_humidity is None
    assert measures.total_volatile_organic_component_index is None
    assert measures.raw_total_volatile_organic_component is None
    assert measures.nitrogen_index is None
    assert measures.raw_nitrogen is None
    assert measures.battery_percentage is None
    assert measures.battery_voltage is None
    assert measures.charge_voltage is None


async def test_v1_zero_measures(responses: aioresponses) -> None:
    """Test that zero remains distinct from an omitted V1 measure."""
    measures = await get_v1_measures(responses, "measures_zero.json")
    assert measures.signal_strength == 0
    assert measures.rco2 == 0
    assert measures.pm01 == 0
    assert measures.pm02 == 0
    assert measures.pm10 == 0
    assert measures.pm003_count == 0
    assert measures.pm005_count == 0
    assert measures.pm01_count == 0
    assert measures.pm02_count == 0
    assert measures.pm50_count == 0
    assert measures.pm10_count == 0
    assert measures.ambient_temperature == 0
    assert measures.relative_humidity == 0
    assert measures.total_volatile_organic_component_index == 0
    assert measures.raw_total_volatile_organic_component == 0
    assert measures.nitrogen_index == 0
    assert measures.raw_nitrogen == 0
    assert measures.battery_percentage == 0
    assert measures.battery_voltage == 0
    assert measures.charge_voltage == 0


@pytest.mark.parametrize("missing", ["serialNumber", "model", "firmware", "boot"])
async def test_v1_measures_requires_identity(
    responses: aioresponses, missing: str
) -> None:
    """Test required V1 identity fields."""
    payload: dict[str, Any] = {
        "serialNumber": "84fce612f5b8",
        "model": "P-1PSG",
        "firmware": "1.0.0",
        "boot": 1,
    }
    del payload[missing]
    responses.get(f"{MOCK_URL}/api/v1/measures", payload=payload)
    async with v1_client() as client:
        with pytest.raises(AirGradientParseError):
            await client.get_current_measures()


async def test_v1_measures_malformed_json(responses: aioresponses) -> None:
    """Test malformed successful V1 response handling."""
    responses.get(f"{MOCK_URL}/api/v1/measures", body="{")
    async with v1_client() as client:
        with pytest.raises(AirGradientParseError):
            await client.get_current_measures()


async def test_v1_does_not_use_boot_count_fallback(
    responses: aioresponses,
) -> None:
    """Test that bootCount fallback remains limited to legacy payloads."""
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        payload={
            "serialNumber": "84fce612f5b8",
            "model": "P-1PSG",
            "firmware": "1.0.0",
            "bootCount": 1,
        },
    )
    async with v1_client() as client:
        with pytest.raises(AirGradientParseError):
            await client.get_current_measures()


async def test_v1_optional_measures_can_return(
    responses: aioresponses,
) -> None:
    """Test omitted optional values can reappear on a later response."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/measures",
        body=load_fixture("v1/measures_full.json"),
    )
    async with v1_client() as client:
        minimal = await client.get_current_measures()
        full = await client.get_current_measures()

    assert minimal.pm02 is None
    assert full.pm02 == 2.5
    assert full.battery_percentage == 87


async def test_v1_go_config(responses: aioresponses) -> None:
    """Test Go config and typed correction parsing."""
    add_v1_probe(responses)
    responses.get(f"{MOCK_URL}/api/v1/config", body=load_fixture("v1/config_go.json"))
    async with v1_client() as client:
        config = await client.get_config()

    assert config.pm_standard is PmStandard.UGM3
    assert config.temperature_unit is TemperatureUnit.CELSIUS
    assert config.measurement_interval == 10
    assert config.gps_mode is GpsMode.TRACKING
    assert config.gps_interval == 5
    assert config.front_led_brightness == 1
    assert config.back_led_brightness == 2
    assert config.touch_led_intensity == 2
    assert config.buzzer_enabled is True
    assert config.cloud_connection is True
    assert config.post_data_to_airgradient is None
    assert config.configuration_control is ConfigurationControl.BOTH
    assert config.co2_automatic_baseline_calibration_days == 7
    assert config.tvoc_learning_offset == 12
    assert config.nox_learning_offset == 12
    assert ConfigurationControl.NOT_INITIALIZED is ConfigurationControl.BOTH
    assert config.corrections is not None
    assert config.corrections.pm25 is not None
    assert (
        config.corrections.pm25.correction_algorithm
        is CorrectionAlgorithm.CUSTOM_VIA_PM25_RAW
    )
    assert config.corrections.pm25.slr is not None
    assert config.corrections.pm25.slr.intercept == 1.5
    assert config.corrections.pm25.slr.scaling_factor == 0.75
    assert config.corrections.pm25.slr.use_epa_2021 is True
    assert config.corrections.temperature is not None
    assert config.corrections.temperature.slr is not None
    assert config.corrections.temperature.slr.intercept == -1.0
    assert config.corrections.temperature.slr.scaling_factor == 1.1
    assert config.corrections.humidity is not None
    assert config.corrections.humidity.slr is None


async def test_v1_go_config_zero_values(responses: aioresponses) -> None:
    """Test valid zero-valued Go config fields."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={
            "measurementInterval": 1,
            "gpsMode": "off",
            "gpsInterval": 1,
            "frontLedBrightness": 0,
            "backLedBrightness": 0,
            "touchLedIntensity": 0,
            "buzzerEnabled": False,
        },
    )
    async with v1_client() as client:
        config = await client.get_config()

    assert config.measurement_interval == 1
    assert config.gps_mode is GpsMode.OFF
    assert config.gps_interval == 1
    assert config.front_led_brightness == 0
    assert config.back_led_brightness == 0
    assert config.touch_led_intensity == 0
    assert config.buzzer_enabled is False


async def test_v1_partial_config(responses: aioresponses) -> None:
    """Test partial generic V1 config normalization."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config", body=load_fixture("v1/config_partial.json")
    )
    async with v1_client() as client:
        config = await client.get_config()

    assert config.configuration_control is ConfigurationControl.LOCAL
    assert config.post_data_to_airgradient is False
    assert config.led_bar_mode is LedBarMode.PM
    assert config.co2_automatic_baseline_calibration_days == 8
    assert config.pm_standard is None
    assert config.cloud_connection is None
    assert config.measurement_interval is None
    assert config.gps_mode is None
    assert config.gps_interval is None
    assert config.front_led_brightness is None
    assert config.back_led_brightness is None
    assert config.touch_led_intensity is None
    assert config.buzzer_enabled is None


async def test_v1_config_ignores_unknown_fields(responses: aioresponses) -> None:
    """Test forward-compatible additive config fields."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={"pmStandard": "ugm3", "futureField": "ignored"},
    )
    async with v1_client() as client:
        config = await client.get_config()

    assert config.pm_standard is PmStandard.UGM3


async def test_v1_additional_correction_algorithms(
    responses: aioresponses,
) -> None:
    """Test EPA and nullable correction settings."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={
            "configurationControl": "cloud",
            "corrections": {
                "pm25": {"correctionAlgorithm": "epa_2021", "slr": None},
                "temperature": {"correctionAlgorithm": "none", "slr": None},
                "humidity": {
                    "correctionAlgorithm": "custom",
                    "slr": {"intercept": 2.0, "scalingFactor": 0.9},
                },
            },
        },
    )
    async with v1_client() as client:
        config = await client.get_config()

    assert config.configuration_control is ConfigurationControl.CLOUD
    assert config.corrections is not None
    assert config.corrections.pm25 is not None
    assert config.corrections.pm25.correction_algorithm is CorrectionAlgorithm.EPA_2021
    assert config.corrections.temperature is not None
    assert (
        config.corrections.temperature.correction_algorithm is CorrectionAlgorithm.NONE
    )
    assert config.corrections.humidity is not None
    assert (
        config.corrections.humidity.correction_algorithm is CorrectionAlgorithm.CUSTOM
    )
    assert config.corrections.humidity.slr is not None
    assert config.corrections.humidity.slr.intercept == 2.0
    assert config.corrections.humidity.slr.scaling_factor == 0.9


async def test_v1_none_corrections(responses: aioresponses) -> None:
    """Test nullable SLR settings for the none algorithms."""
    add_v1_probe(responses)
    responses.get(
        f"{MOCK_URL}/api/v1/config",
        payload={
            "corrections": {
                "pm25": {"correctionAlgorithm": "none", "slr": None},
                "temperature": {"correctionAlgorithm": "none", "slr": None},
                "humidity": {"correctionAlgorithm": "none", "slr": None},
            }
        },
    )
    async with v1_client() as client:
        config = await client.get_config()

    assert config.corrections is not None
    assert config.corrections.pm25 is not None
    assert config.corrections.pm25.slr is None
    assert config.corrections.temperature is not None
    assert config.corrections.temperature.slr is None
    assert config.corrections.humidity is not None
    assert config.corrections.humidity.slr is None


@pytest.mark.parametrize(
    ("function", "expected_path", "expected_method", "expected_data", "status"),
    [
        (
            lambda client: client.set_temperature_unit(TemperatureUnit.FAHRENHEIT),
            "config",
            METH_PUT,
            {"temperatureUnit": "f"},
            202,
        ),
        (
            lambda client: client.set_pm_standard(PmStandard.USAQI),
            "config",
            METH_PUT,
            {"pmStandard": "us-aqi"},
            202,
        ),
        (
            lambda client: client.set_configuration_control(ConfigurationControl.LOCAL),
            "config",
            METH_PUT,
            {"configurationControl": "local"},
            202,
        ),
        (
            lambda client: client.set_led_bar_mode(LedBarMode.CO2),
            "config",
            METH_PUT,
            {"ledMode": "co2"},
            202,
        ),
        (
            lambda client: client.enable_sharing_data(enable=True),
            "config",
            METH_PUT,
            {"postDataToCloud": True},
            202,
        ),
        (
            lambda client: client.set_co2_automatic_baseline_calibration(8),
            "config",
            METH_PUT,
            {"co2AbcDays": 8},
            202,
        ),
        (
            lambda client: client.set_cloud_connection(False),
            "config",
            METH_PUT,
            {"cloudConnection": False},
            202,
        ),
        (
            lambda client: client.set_display_brightness(50),
            "config",
            METH_PUT,
            {"displayBrightness": 50},
            202,
        ),
        (
            lambda client: client.set_led_bar_brightness(50),
            "config",
            METH_PUT,
            {"ledBarBrightness": 50},
            202,
        ),
        (
            lambda client: client.set_nox_learning_offset(12),
            "config",
            METH_PUT,
            {"noxLearningOffset": 12},
            202,
        ),
        (
            lambda client: client.set_tvoc_learning_offset(12),
            "config",
            METH_PUT,
            {"tvocLearningOffset": 12},
            202,
        ),
        (
            lambda client: client.request_co2_calibration(),
            "actions/calibrate-co2",
            METH_POST,
            None,
            200,
        ),
        (
            lambda client: client.request_led_bar_test(),
            "actions/test-leds",
            METH_POST,
            None,
            200,
        ),
    ],
)
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
    async with v1_client() as client:
        await function(client)
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
    async with v1_client() as client:
        with pytest.raises(error_type) as raised:
            await client.set_temperature_unit(TemperatureUnit.CELSIUS)

    error = raised.value
    assert isinstance(error, error_type)
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
    async with v1_client() as client:
        with pytest.raises(AirGradientBusyError) as raised:
            await client.set_pm_standard(PmStandard.UGM3)

    assert raised.value.field is None


async def test_v1_malformed_error_is_connection_error(
    responses: aioresponses,
) -> None:
    """Test that malformed error envelopes remain generic HTTP failures."""
    add_v1_probe(responses)
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=404,
        body='{"error":{"code":3}}',
        headers={"Content-Type": "application/json"},
    )
    async with v1_client() as client:
        with pytest.raises(AirGradientConnectionError):
            await client.set_pm_standard(PmStandard.UGM3)


async def test_v1_missing_error_envelope_is_connection_error(
    responses: aioresponses,
) -> None:
    """Test that JSON without an error envelope remains a generic failure."""
    add_v1_probe(responses)
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=400,
        body='{"message":"rejected"}',
        headers={"Content-Type": "application/json"},
    )
    async with v1_client() as client:
        with pytest.raises(AirGradientConnectionError):
            await client.set_pm_standard(PmStandard.UGM3)


async def test_v1_config_requires_accepted_status(
    responses: aioresponses,
) -> None:
    """Test that V1 config accepts 202 rather than any 2xx response."""
    add_v1_probe(responses)
    responses.put(f"{MOCK_URL}/api/v1/config", status=200, body="")
    async with v1_client() as client:
        with pytest.raises(AirGradientConnectionError):
            await client.set_pm_standard(PmStandard.UGM3)


async def test_selected_v1_bare_404_is_connection_error(
    responses: aioresponses,
) -> None:
    """Test an unstructured operation 404 after V1 selection."""
    add_v1_probe(responses)
    responses.put(
        f"{MOCK_URL}/api/v1/config",
        status=404,
        body="Not found",
        headers={"Content-Type": "text/plain"},
    )
    async with v1_client() as client:
        with pytest.raises(AirGradientConnectionError):
            await client.set_pm_standard(PmStandard.UGM3)
