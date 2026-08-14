"""Asynchronous Python client for AirGradient."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import metadata
import socket
from typing import TYPE_CHECKING, Any, TypeVar, cast

from aiohttp import ClientError, ClientSession
from aiohttp.hdrs import METH_GET, METH_POST, METH_PUT
from mashumaro import MissingField
import orjson
from yarl import URL

from .exceptions import (
    AirGradientBadRequestError,
    AirGradientBusyError,
    AirGradientConnectionError,
    AirGradientForbiddenError,
    AirGradientHttpError,
    AirGradientInternalError,
    AirGradientNotSupportedError,
    AirGradientParseError,
)
from .models import (
    ApiVersion,
    Config,
    ConfigurationControl,
    GpsMode,
    LedBarMode,
    Measures,
    PmStandard,
    TemperatureUnit,
    VersionCheck,
)
from .parsers import parse_config_json, parse_measures_json
from .util import get_model_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self


VERSION = metadata.version(__package__)
_ModelT = TypeVar("_ModelT")


class _BareRouteNotFoundError(Exception):
    """An unstructured HTTP 404 from an unknown route."""


def _parse_response(body: str, parser: Callable[[str], _ModelT]) -> _ModelT:
    """Parse a successful response into a normalized model."""
    try:
        return parser(body)
    except (KeyError, MissingField, TypeError, ValueError) as err:
        msg = "Unable to parse AirGradient response"
        raise AirGradientParseError(msg) from err


@dataclass(frozen=True)
class _Api:
    """Routes and fields for an AirGradient Local API version."""

    version: ApiVersion
    measures_path: str
    config_path: str
    config_status: int
    config_fields: dict[str, str]


_LEGACY_API = _Api(
    version=ApiVersion.LEGACY,
    measures_path="measures/current",
    config_path="config",
    config_status=200,
    config_fields={
        "pm_standard": "pmStandard",
        "temperature_unit": "temperatureUnit",
        "configuration_control": "configurationControl",
        "led_bar_mode": "ledBarMode",
        "display_brightness": "displayBrightness",
        "led_bar_brightness": "ledBarBrightness",
        "sharing_data": "postDataToAirGradient",
        "co2_abc_days": "abcDays",
        "nox_learning_offset": "noxLearningOffset",
        "tvoc_learning_offset": "tvocLearningOffset",
    },
)
_V1_API = _Api(
    version=ApiVersion.V1,
    measures_path="api/v1/measures",
    config_path="api/v1/config",
    config_status=202,
    config_fields={
        "pm_standard": "pmStandard",
        "temperature_unit": "temperatureUnit",
        "configuration_control": "configurationControl",
        "led_bar_mode": "ledMode",
        "display_brightness": "displayBrightness",
        "led_bar_brightness": "ledBarBrightness",
        "sharing_data": "postDataToCloud",
        "co2_abc_days": "co2AbcDays",
        "nox_learning_offset": "noxLearningOffset",
        "tvoc_learning_offset": "tvocLearningOffset",
        "cloud_connection": "cloudConnection",
        "measurement_interval": "measurementInterval",
        "gps_mode": "gpsMode",
        "front_led_brightness": "frontLedBrightness",
        "back_led_brightness": "backLedBrightness",
        "touch_led_intensity": "touchLedIntensity",
        "buzzer_enabled": "buzzerEnabled",
    },
)


@dataclass(init=False)
class AirGradientClient:  # pylint: disable=too-many-public-methods
    """Main class for handling connections with AirGradient."""

    host: str
    session: ClientSession | None = None
    request_timeout: float = 10
    _close_session: bool = False

    def __init__(
        self,
        host: str,
        session: ClientSession | None = None,
        request_timeout: float = 10,
        _close_session: bool = False,  # noqa: FBT001, FBT002
        api_version: ApiVersion | None = None,
    ) -> None:
        """Initialize an AirGradient client.

        The API version hint only changes probe order. An API is selected after
        its measures response succeeds and parses.
        """
        self.host = host
        self.session = session
        self.request_timeout = request_timeout
        self._close_session = _close_session
        self._api_version_hint = (
            api_version if isinstance(api_version, ApiVersion) else None
        )
        self._api: _Api | None = None
        self._detection_lock = asyncio.Lock()
        self._probe_measures: Measures | None = None
        self._probe_measures_pending = False

    @property
    def api_version(self) -> ApiVersion | None:
        """Return the selected API version, or ``None`` before detection."""
        if self._api is None:
            return None
        return self._api.version

    async def _request(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        path_or_url: str | URL,
        *,
        method: str = METH_GET,
        data: dict[str, Any] | None = None,
        expected_status: int = 200,
        api_version: ApiVersion | None = None,
        detecting: bool = False,
    ) -> str:
        """Request a device-relative path or absolute URL within the timeout."""
        headers = {
            "User-Agent": f"PythonAirGradient/{VERSION}",
            "Accept": "application/json",
        }
        url = (
            URL.build(scheme="http", host=self.host).joinpath(path_or_url)
            if isinstance(path_or_url, str)
            else path_or_url
        )

        if self.session is None:
            self.session = ClientSession()
            self._close_session = True

        try:
            async with asyncio.timeout(self.request_timeout):
                response = await self.session.request(
                    method,
                    url,
                    headers=headers,
                    json=data,
                )
                try:
                    body = await response.text()
                    content_type = response.headers.get("Content-Type", "")
                    if response.status != expected_status:
                        self._raise_http_error(
                            status=response.status,
                            content_type=content_type,
                            body=body,
                            api_version=api_version,
                            detecting=detecting,
                        )
                    return body
                finally:
                    response.release()
        except TimeoutError as err:
            msg = "Timeout occurred while communicating with the device"
            raise AirGradientConnectionError(msg) from err
        except (ClientError, socket.gaierror) as err:
            msg = "Error occurred while communicating with the device"
            raise AirGradientConnectionError(msg) from err

    @staticmethod
    def _raise_http_error(
        *,
        status: int,
        content_type: str,
        body: str,
        api_version: ApiVersion | None,
        detecting: bool,
    ) -> None:
        """Map an unsuccessful HTTP response to the public exception hierarchy."""
        if api_version is ApiVersion.V1:
            error = AirGradientClient._structured_v1_error(
                status=status,
                content_type=content_type,
                body=body,
            )
            if error is not None:
                raise error

        if (
            detecting
            and status == 404
            and not AirGradientClient._looks_like_json(content_type, body)
        ):
            raise _BareRouteNotFoundError

        msg = "Unexpected response from AirGradient"
        raise AirGradientConnectionError(
            msg,
            {
                "status": status,
                "Content-Type": content_type,
                "response": body,
            },
        )

    @staticmethod
    def _structured_v1_error(
        *, status: int, content_type: str, body: str
    ) -> AirGradientHttpError | None:
        """Return a structured Local API V1 error when the envelope is valid."""
        try:
            payload = orjson.loads(body)  # pylint: disable=no-member
        except orjson.JSONDecodeError:  # pylint: disable=no-member
            return None
        envelope = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(envelope, dict):
            return None
        code = envelope.get("code")
        field = envelope.get("field")
        message = envelope.get("message")
        if not (
            isinstance(code, str)
            and (field is None or isinstance(field, str))
            and (message is None or isinstance(message, str))
        ):
            return None

        error_types: dict[int, type[AirGradientHttpError]] = {
            400: AirGradientBadRequestError,
            403: AirGradientForbiddenError,
            404: AirGradientNotSupportedError,
            500: AirGradientInternalError,
            503: AirGradientBusyError,
        }
        error_type = error_types.get(status, AirGradientHttpError)
        return error_type(
            status=status,
            code=code,
            field=field,
            message=message,
            content_type=content_type,
            body=body,
        )

    @staticmethod
    def _looks_like_json(content_type: str, body: str) -> bool:
        """Return whether an error appears intended to contain JSON."""
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            return True
        return body.lstrip().startswith(("{", "["))

    async def _get_measures(self, api: _Api, *, detecting: bool = False) -> Measures:
        """Get current measures using a selected API definition."""
        body = await self._request(
            api.measures_path,
            api_version=api.version,
            detecting=detecting,
        )
        return parse_measures_json(body, api_version=api.version)

    async def _ensure_api(self) -> _Api:
        """Detect and retain one API definition for this client lifetime."""
        if self._api is not None:
            return self._api

        async with self._detection_lock:
            if self._api is not None:
                return self._api

            if self._api_version_hint is ApiVersion.V1:
                candidates = (_V1_API, _LEGACY_API)
            else:
                candidates = (_LEGACY_API, _V1_API)

            first_api = candidates[0]
            try:
                measures = await self._get_measures(first_api, detecting=True)
            except _BareRouteNotFoundError:
                selected_api = candidates[1]
                measures = await self._get_measures(selected_api)
            else:
                selected_api = first_api

            self._api = selected_api
            self._probe_measures = measures
            self._probe_measures_pending = True
            return selected_api

    async def get_current_measures(self) -> Measures:
        """Get current measures from AirGradient."""
        started_unselected = self._api is None
        api = await self._ensure_api()
        if started_unselected:
            self._probe_measures_pending = False
            return cast("Measures", self._probe_measures)
        if self._probe_measures_pending:
            self._probe_measures_pending = False
            return cast("Measures", self._probe_measures)
        return await self._get_measures(api)

    async def get_config(self) -> Config:
        """Get config from AirGradient device."""
        api = await self._ensure_api()
        body = await self._request(api.config_path, api_version=api.version)
        return parse_config_json(body, api_version=api.version)

    async def _set_config(self, field: str, value: Any) -> None:
        """Set config on AirGradient device."""
        api = await self._ensure_api()
        wire_field = api.config_fields.get(field)
        if wire_field is None:
            raise AirGradientNotSupportedError(
                status=404,
                code="not_found",
                message=f"{field} is not supported by the selected API",
            )
        await self._request(
            api.config_path,
            method=METH_PUT,
            data={wire_field: value},
            expected_status=api.config_status,
            api_version=api.version,
        )

    async def set_pm_standard(self, pm_standard: PmStandard) -> None:
        """Set PM standard on AirGradient device."""
        await self._set_config("pm_standard", pm_standard)

    async def set_temperature_unit(self, temperature_unit: TemperatureUnit) -> None:
        """Set temperature unit on AirGradient device."""
        await self._set_config("temperature_unit", temperature_unit)

    async def set_configuration_control(
        self, configuration_control: ConfigurationControl
    ) -> None:
        """Set configuration control on AirGradient device."""
        await self._set_config("configuration_control", configuration_control)

    async def set_led_bar_mode(self, led_bar_mode: LedBarMode) -> None:
        """Set LED bar mode on AirGradient device."""
        await self._set_config("led_bar_mode", led_bar_mode)

    async def request_co2_calibration(self) -> None:
        """Request CO2 calibration on AirGradient device."""
        api = await self._ensure_api()
        if api.version is ApiVersion.V1:
            await self._request(
                "api/v1/actions/calibrate-co2",
                method=METH_POST,
                api_version=api.version,
            )
            return
        await self._request(
            api.config_path,
            method=METH_PUT,
            data={"co2CalibrationRequested": True},
            api_version=api.version,
        )

    async def request_led_bar_test(self) -> None:
        """Request LED bar test on AirGradient device."""
        api = await self._ensure_api()
        if api.version is ApiVersion.V1:
            await self._request(
                "api/v1/actions/test-leds",
                method=METH_POST,
                api_version=api.version,
            )
            return
        await self._request(
            api.config_path,
            method=METH_PUT,
            data={"ledBarTestRequested": True},
            api_version=api.version,
        )

    async def set_display_brightness(self, brightness: int) -> None:
        """Set display brightness on AirGradient device."""
        await self._set_config("display_brightness", brightness)

    async def set_led_bar_brightness(self, brightness: int) -> None:
        """Set LED bar brightness on AirGradient device."""
        await self._set_config("led_bar_brightness", brightness)

    async def enable_sharing_data(self, *, enable: bool) -> None:
        """Enable or disable sharing data on AirGradient device."""
        await self._set_config("sharing_data", enable)

    async def set_co2_automatic_baseline_calibration(self, days: int) -> None:
        """Set CO2 automatic baseline calibration on AirGradient device."""
        await self._set_config("co2_abc_days", days)

    async def set_nox_learning_offset(self, offset: int) -> None:
        """Set NOx learning offset on AirGradient device."""
        await self._set_config("nox_learning_offset", offset)

    async def set_tvoc_learning_offset(self, offset: int) -> None:
        """Set TVOC learning offset on AirGradient device."""
        await self._set_config("tvoc_learning_offset", offset)

    async def set_cloud_connection(self, enabled: bool) -> None:  # noqa: FBT001
        """Enable or disable the V1 product cloud connection."""
        await self._set_config("cloud_connection", enabled)

    async def set_measurement_interval(self, interval: int) -> None:
        """Set the V1 measurement interval in seconds."""
        await self._set_config("measurement_interval", interval)

    async def set_gps_mode(self, gps_mode: GpsMode) -> None:
        """Set the V1 GPS operating mode."""
        await self._set_config("gps_mode", gps_mode)

    async def set_front_led_brightness(self, brightness: int) -> None:
        """Set the V1 front LED brightness."""
        await self._set_config("front_led_brightness", brightness)

    async def set_back_led_brightness(self, brightness: int) -> None:
        """Set the V1 back LED brightness."""
        await self._set_config("back_led_brightness", brightness)

    async def set_touch_led_intensity(self, intensity: int) -> None:
        """Set the V1 touch LED intensity."""
        await self._set_config("touch_led_intensity", intensity)

    async def set_buzzer_enabled(self, enabled: bool) -> None:  # noqa: FBT001
        """Enable or disable the V1 buzzer."""
        await self._set_config("buzzer_enabled", enabled)

    async def get_latest_firmware_version(
        self,
        serial_number: str,
        *,
        model: str | None = None,
    ) -> str:
        """Get the latest firmware version for an AirGradient model."""
        if model is not None and get_model_name(model) == "AirGradient Go":
            firmware_path = f"sensors/airgradient:{serial_number}/go/firmware"
        else:
            firmware_path = f"sensors/airgradient:{serial_number}/generic/os/firmware"

        url = URL.build(scheme="http", host="hw.airgradient.com").joinpath(
            firmware_path
        )
        response = await self._request(url)
        return _parse_response(
            response,
            lambda body: VersionCheck.from_json(body).target_version,
        )

    async def close(self) -> None:
        """Close open client session."""
        if self.session and self._close_session:
            await self.session.close()

    async def __aenter__(self) -> Self:
        """Async enter.

        Returns
        -------
            The AirGradientClient object.

        """
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Async exit.

        Args:
        ----
            _exc_info: Exec type.

        """
        await self.close()
