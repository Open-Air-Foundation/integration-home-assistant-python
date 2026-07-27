"""Asynchronous Python client for AirGradient."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import metadata
import socket
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

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


class _Backend:
    """Base implementation shared by Local API backends."""

    api_version: ClassVar[ApiVersion]
    measures_path: ClassVar[str]
    config_path: ClassVar[str]
    config_status: ClassVar[int]
    config_fields: ClassVar[dict[str, str]]

    def __init__(self, client: AirGradientClient) -> None:
        self._client = client

    async def get_measures(self, *, detecting: bool = False) -> Measures:
        """Get and normalize current measures."""
        body = await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            self.measures_path,
            api_version=self.api_version,
            detecting=detecting,
        )
        return _parse_response(body, self._parse_measures)

    async def get_config(self) -> Config:
        """Get and normalize device config."""
        body = await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            self.config_path,
            api_version=self.api_version,
        )
        return _parse_response(body, self._parse_config)

    async def set_config(self, field: str, value: Any) -> None:
        """Set one normalized config field."""
        wire_field = self.config_fields.get(field)
        if wire_field is None:
            raise AirGradientNotSupportedError(
                status=404,
                code="not_found",
                message=f"{field} is not supported by the selected API",
            )
        await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            self.config_path,
            method=METH_PUT,
            data={wire_field: value},
            expected_status=self.config_status,
            api_version=self.api_version,
        )

    def _parse_measures(self, body: str) -> Measures:
        """Parse a backend-specific measures response."""
        raise NotImplementedError

    def _parse_config(self, body: str) -> Config:
        """Parse a backend-specific config response."""
        raise NotImplementedError

    async def request_co2_calibration(self) -> None:
        """Request CO2 calibration."""
        raise NotImplementedError

    async def request_led_bar_test(self) -> None:
        """Request an LED bar test."""
        raise NotImplementedError

    async def set_cloud_connection(self, enabled: bool) -> None:  # noqa: FBT001
        """Set the product cloud connection."""
        raise NotImplementedError


class _LegacyBackend(_Backend):
    """Legacy AirGradient Local API backend."""

    api_version = ApiVersion.LEGACY
    measures_path = "measures/current"
    config_path = "config"
    config_status = 200
    config_fields: ClassVar[dict[str, str]] = {
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
    }

    def _parse_measures(self, body: str) -> Measures:
        return parse_measures_json(body, api_version=self.api_version)

    def _parse_config(self, body: str) -> Config:
        return parse_config_json(body, api_version=self.api_version)

    async def request_co2_calibration(self) -> None:
        await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            self.config_path,
            method=METH_PUT,
            data={"co2CalibrationRequested": True},
            api_version=self.api_version,
        )

    async def request_led_bar_test(self) -> None:
        await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            self.config_path,
            method=METH_PUT,
            data={"ledBarTestRequested": True},
            api_version=self.api_version,
        )

    async def set_cloud_connection(self, enabled: bool) -> None:  # noqa: FBT001
        del enabled
        raise AirGradientNotSupportedError(
            status=404,
            code="not_found",
            message="Cloud connection is not supported by the legacy API",
        )


class _V1Backend(_Backend):
    """Version 1 AirGradient Local API backend."""

    api_version = ApiVersion.V1
    measures_path = "api/v1/measures"
    config_path = "api/v1/config"
    config_status = 202
    config_fields: ClassVar[dict[str, str]] = {
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
        "gps_interval": "gpsInterval",
        "front_led_brightness": "frontLedBrightness",
        "back_led_brightness": "backLedBrightness",
        "touch_led_intensity": "touchLedIntensity",
        "buzzer_enabled": "buzzerEnabled",
    }

    def _parse_measures(self, body: str) -> Measures:
        return parse_measures_json(body, api_version=self.api_version)

    def _parse_config(self, body: str) -> Config:
        return parse_config_json(body, api_version=self.api_version)

    async def _request_action(self, action: str) -> None:
        await self._client._request_device(  # noqa: SLF001  # pylint: disable=protected-access
            f"api/v1/actions/{action}",
            method=METH_POST,
            api_version=self.api_version,
        )

    async def request_co2_calibration(self) -> None:
        await self._request_action("calibrate-co2")

    async def request_led_bar_test(self) -> None:
        await self._request_action("test-leds")

    async def set_cloud_connection(self, enabled: bool) -> None:  # noqa: FBT001
        await self.set_config("cloud_connection", enabled)


@dataclass(init=False)
class AirGradientClient:
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

        The API version hint only changes probe order. A backend is selected after
        its measures response succeeds and parses.
        """
        self.host = host
        self.session = session
        self.request_timeout = request_timeout
        self._close_session = _close_session
        self._api_version_hint = (
            api_version if isinstance(api_version, ApiVersion) else None
        )
        self._backend: _Backend | None = None
        self._detection_lock = asyncio.Lock()
        self._probe_measures: Measures | None = None
        self._probe_measures_pending = False

    @property
    def api_version(self) -> ApiVersion | None:
        """Return the selected API version, or ``None`` before detection."""
        if self._backend is None:
            return None
        return self._backend.api_version

    async def _request(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        url: URL,
        *,
        method: str = METH_GET,
        data: dict[str, Any] | None = None,
        expected_status: int = 200,
        api_version: ApiVersion | None = None,
        detecting: bool = False,
    ) -> str:
        """Perform one HTTP request and read its body within the timeout."""
        headers = {
            "User-Agent": f"PythonAirGradient/{VERSION}",
            "Accept": "application/json",
        }

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

    async def _request_device(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        uri: str,
        *,
        method: str = METH_GET,
        data: dict[str, Any] | None = None,
        expected_status: int = 200,
        api_version: ApiVersion | None = None,
        detecting: bool = False,
    ) -> str:
        """Perform a request against the device's fixed port 80 Local API."""
        url = URL.build(scheme="http", host=self.host).joinpath(uri)
        return await self._request(
            url,
            method=method,
            data=data,
            expected_status=expected_status,
            api_version=api_version,
            detecting=detecting,
        )

    async def _ensure_backend(self) -> _Backend:
        """Detect and retain one backend for this client lifetime."""
        if self._backend is not None:
            return self._backend

        async with self._detection_lock:
            if self._backend is not None:
                return self._backend

            if self._api_version_hint is ApiVersion.V1:
                candidates: tuple[type[_Backend], ...] = (_V1Backend, _LegacyBackend)
            else:
                candidates = (_LegacyBackend, _V1Backend)

            first_backend = candidates[0](self)
            try:
                measures = await first_backend.get_measures(detecting=True)
            except _BareRouteNotFoundError:
                selected_backend = candidates[1](self)
                measures = await selected_backend.get_measures()
            else:
                selected_backend = first_backend

            self._backend = selected_backend
            self._probe_measures = measures
            self._probe_measures_pending = True
            return selected_backend

    async def get_current_measures(self) -> Measures:
        """Get current measures from AirGradient."""
        started_unselected = self._backend is None
        backend = await self._ensure_backend()
        if started_unselected:
            self._probe_measures_pending = False
            return cast("Measures", self._probe_measures)
        if self._probe_measures_pending:
            self._probe_measures_pending = False
            return cast("Measures", self._probe_measures)
        return await backend.get_measures()

    async def get_config(self) -> Config:
        """Get config from AirGradient device."""
        backend = await self._ensure_backend()
        return await backend.get_config()

    async def _set_config(self, field: str, value: Any) -> None:
        """Set config on AirGradient device."""
        backend = await self._ensure_backend()
        await backend.set_config(field, value)

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
        backend = await self._ensure_backend()
        await backend.request_co2_calibration()

    async def request_led_bar_test(self) -> None:
        """Request LED bar test on AirGradient device."""
        backend = await self._ensure_backend()
        await backend.request_led_bar_test()

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
        backend = await self._ensure_backend()
        await backend.set_cloud_connection(enabled)

    async def set_measurement_interval(self, interval: int) -> None:
        """Set the V1 measurement interval in seconds."""
        await self._set_config("measurement_interval", interval)

    async def set_gps_mode(self, gps_mode: GpsMode) -> None:
        """Set the V1 GPS operating mode."""
        await self._set_config("gps_mode", gps_mode)

    async def set_gps_interval(self, interval: int) -> None:
        """Set the V1 GPS interval in seconds."""
        await self._set_config("gps_interval", interval)

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

    async def get_latest_firmware_version(self, serial_number: str) -> str:
        """Get the latest firmware version from AirGradient."""
        url = URL.build(scheme="http", host="hw.airgradient.com").joinpath(
            f"sensors/airgradient:{serial_number}/generic/os/firmware"
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
