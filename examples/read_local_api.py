# ruff: noqa: T201
"""Read measures and config from an AirGradient device on the local network.

Read-only examples:
    poetry run python examples/read_local_api.py --ip 192.168.1.123
    poetry run python examples/read_local_api.py --serial 84fce612f5b8

Config PUT example:
    poetry run python examples/read_local_api.py --serial 84fce612f5b8 \
        --put-config --pm-standard ugm3 --temperature-unit c

CO2 calibration example:
    poetry run python examples/read_local_api.py --serial 84fce612f5b8 \
        --calibrate-co2

LED test example:
    poetry run python examples/read_local_api.py --serial 84fce612f5b8 \
        --test-leds

Config writes require the explicit ``--put-config`` flag. Available typed
options are ``--pm-standard``, ``--temperature-unit``,
``--configuration-control``, ``--led-bar-mode``, ``--display-brightness``,
``--led-bar-brightness``, ``--sharing-data``/``--no-sharing-data``,
``--co2-abc-days``, ``--nox-learning-offset``, ``--tvoc-learning-offset``, and
``--cloud-connection``/``--no-cloud-connection``. V1 options also include
``--measurement-interval``, ``--gps-mode``, ``--front-led-brightness``,
``--back-led-brightness``,
``--touch-led-intensity``, and ``--buzzer-enabled``/``--no-buzzer-enabled``.
Run with ``--help`` for the accepted values. ``--calibrate-co2`` and
``--test-leds`` submit real actions and are disabled by default.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from ipaddress import ip_address
import re
import sys

import orjson

from airgradient import (
    AirGradientClient,
    AirGradientError,
    Config,
    ConfigurationControl,
    GpsMode,
    LedBarMode,
    Measures,
    PmStandard,
    TemperatureUnit,
)


@dataclass(frozen=True)
class ConfigUpdates:
    """Typed config updates requested by the caller."""

    pm_standard: PmStandard | None
    temperature_unit: TemperatureUnit | None
    configuration_control: ConfigurationControl | None
    led_bar_mode: LedBarMode | None
    display_brightness: int | None
    led_bar_brightness: int | None
    sharing_data: bool | None
    co2_abc_days: int | None
    nox_learning_offset: int | None
    tvoc_learning_offset: int | None
    cloud_connection: bool | None
    measurement_interval: int | None
    gps_mode: GpsMode | None
    front_led_brightness: int | None
    back_led_brightness: int | None
    touch_led_intensity: int | None
    buzzer_enabled: bool | None

    def has_updates(self) -> bool:
        """Return whether at least one config update was supplied."""
        return any(
            value is not None
            for value in (
                self.pm_standard,
                self.temperature_unit,
                self.configuration_control,
                self.led_bar_mode,
                self.display_brightness,
                self.led_bar_brightness,
                self.sharing_data,
                self.co2_abc_days,
                self.nox_learning_offset,
                self.tvoc_learning_offset,
                self.cloud_connection,
                self.measurement_interval,
                self.gps_mode,
                self.front_led_brightness,
                self.back_led_brightness,
                self.touch_led_intensity,
                self.buzzer_enabled,
            )
        )


@dataclass(frozen=True)
class Options:
    """Validated command-line options."""

    host: str
    expected_serial: str | None
    config_updates: ConfigUpdates | None
    calibrate_co2: bool
    test_leds: bool


def _serial_number(value: str) -> str:
    """Validate a serial number for use in an AirGradient mDNS hostname."""
    serial_number = value.strip()
    if not serial_number or re.fullmatch(r"[A-Za-z0-9-]+", serial_number) is None:
        msg = "serial number must contain only letters, numbers, and hyphens"
        raise argparse.ArgumentTypeError(msg)
    return serial_number


def _ip_address(value: str) -> str:
    """Validate and normalize an IPv4 or IPv6 address."""
    try:
        return str(ip_address(value))
    except ValueError as err:
        msg = f"invalid IP address: {value}"
        raise argparse.ArgumentTypeError(msg) from err


def _parse_args() -> Options:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Read the detected API version, measures, and config.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--ip",
        type=_ip_address,
        help="device IPv4 or IPv6 address",
    )
    target.add_argument(
        "--serial",
        type=_serial_number,
        help="device serial; connects to airgradient_<serial>.local",
    )
    parser.add_argument(
        "--put-config",
        action="store_true",
        help="enable config writes using one or more typed options below",
    )
    parser.add_argument("--pm-standard", choices=[item.value for item in PmStandard])
    parser.add_argument(
        "--temperature-unit", choices=[item.value for item in TemperatureUnit]
    )
    parser.add_argument(
        "--configuration-control",
        choices=[item.value for item in ConfigurationControl],
    )
    parser.add_argument("--led-bar-mode", choices=[item.value for item in LedBarMode])
    parser.add_argument("--display-brightness", type=int)
    parser.add_argument("--led-bar-brightness", type=int)
    parser.add_argument(
        "--sharing-data",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--co2-abc-days", type=int)
    parser.add_argument("--nox-learning-offset", type=int)
    parser.add_argument("--tvoc-learning-offset", type=int)
    parser.add_argument(
        "--cloud-connection",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--measurement-interval", type=int)
    parser.add_argument("--gps-mode", choices=[item.value for item in GpsMode])
    parser.add_argument("--front-led-brightness", type=int)
    parser.add_argument("--back-led-brightness", type=int)
    parser.add_argument("--touch-led-intensity", type=int)
    parser.add_argument(
        "--buzzer-enabled",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--calibrate-co2",
        action="store_true",
        help="submit a CO2 calibration request",
    )
    parser.add_argument(
        "--test-leds",
        action="store_true",
        help="submit an LED test request",
    )
    args = parser.parse_args()

    updates = ConfigUpdates(
        pm_standard=(
            PmStandard(str(args.pm_standard)) if args.pm_standard is not None else None
        ),
        temperature_unit=(
            TemperatureUnit(str(args.temperature_unit))
            if args.temperature_unit is not None
            else None
        ),
        configuration_control=(
            ConfigurationControl(str(args.configuration_control))
            if args.configuration_control is not None
            else None
        ),
        led_bar_mode=(
            LedBarMode(str(args.led_bar_mode))
            if args.led_bar_mode is not None
            else None
        ),
        display_brightness=args.display_brightness,
        led_bar_brightness=args.led_bar_brightness,
        sharing_data=args.sharing_data,
        co2_abc_days=args.co2_abc_days,
        nox_learning_offset=args.nox_learning_offset,
        tvoc_learning_offset=args.tvoc_learning_offset,
        cloud_connection=args.cloud_connection,
        measurement_interval=args.measurement_interval,
        gps_mode=(GpsMode(str(args.gps_mode)) if args.gps_mode is not None else None),
        front_led_brightness=args.front_led_brightness,
        back_led_brightness=args.back_led_brightness,
        touch_led_intensity=args.touch_led_intensity,
        buzzer_enabled=args.buzzer_enabled,
    )
    if args.put_config and not updates.has_updates():
        parser.error("--put-config requires at least one config option")
    if not args.put_config and updates.has_updates():
        parser.error("config options require the explicit --put-config flag")
    config_updates = updates if args.put_config else None

    if args.serial is not None:
        serial_number = str(args.serial)
        return Options(
            host=f"airgradient_{serial_number}.local",
            expected_serial=serial_number,
            config_updates=config_updates,
            calibrate_co2=bool(args.calibrate_co2),
            test_leds=bool(args.test_leds),
        )
    return Options(
        host=str(args.ip),
        expected_serial=None,
        config_updates=config_updates,
        calibrate_co2=bool(args.calibrate_co2),
        test_leds=bool(args.test_leds),
    )


def _print_model(label: str, model: Config | Measures) -> None:
    """Print a normalized model as formatted JSON."""
    print(f"{label}:")
    indent_option = orjson.OPT_INDENT_2  # pylint: disable=no-member
    body = orjson.dumps(  # pylint: disable=no-member
        asdict(model), option=indent_option
    )
    print(body.decode())


async def _put_v1_config(client: AirGradientClient, updates: ConfigUpdates) -> None:
    """Submit V1-specific config values."""
    if updates.measurement_interval is not None:
        await client.set_measurement_interval(updates.measurement_interval)
    if updates.gps_mode is not None:
        await client.set_gps_mode(updates.gps_mode)
    if updates.front_led_brightness is not None:
        await client.set_front_led_brightness(updates.front_led_brightness)
    if updates.back_led_brightness is not None:
        await client.set_back_led_brightness(updates.back_led_brightness)
    if updates.touch_led_intensity is not None:
        await client.set_touch_led_intensity(updates.touch_led_intensity)
    if updates.buzzer_enabled is not None:
        await client.set_buzzer_enabled(updates.buzzer_enabled)


async def _put_config(client: AirGradientClient, updates: ConfigUpdates) -> None:
    """Submit requested config values through the public typed setters."""
    if updates.configuration_control in (
        ConfigurationControl.LOCAL,
        ConfigurationControl.BOTH,
    ):
        await client.set_configuration_control(updates.configuration_control)
    if updates.pm_standard is not None:
        await client.set_pm_standard(updates.pm_standard)
    if updates.temperature_unit is not None:
        await client.set_temperature_unit(updates.temperature_unit)
    await _put_v1_config(client, updates)
    if updates.led_bar_mode is not None:
        await client.set_led_bar_mode(updates.led_bar_mode)
    if updates.display_brightness is not None:
        await client.set_display_brightness(updates.display_brightness)
    if updates.led_bar_brightness is not None:
        await client.set_led_bar_brightness(updates.led_bar_brightness)
    if updates.sharing_data is not None:
        await client.enable_sharing_data(enable=updates.sharing_data)
    if updates.co2_abc_days is not None:
        await client.set_co2_automatic_baseline_calibration(updates.co2_abc_days)
    if updates.nox_learning_offset is not None:
        await client.set_nox_learning_offset(updates.nox_learning_offset)
    if updates.tvoc_learning_offset is not None:
        await client.set_tvoc_learning_offset(updates.tvoc_learning_offset)
    if updates.cloud_connection is not None:
        await client.set_cloud_connection(updates.cloud_connection)
    if updates.configuration_control is ConfigurationControl.CLOUD:
        await client.set_configuration_control(updates.configuration_control)


async def _run(options: Options) -> int:
    """Read and print Local API data."""
    try:
        async with AirGradientClient(options.host) as client:
            measures = await client.get_current_measures()
            if (
                options.expected_serial is not None
                and measures.serial_number.casefold()
                != options.expected_serial.casefold()
            ):
                print(
                    "Serial mismatch: "
                    f"expected {options.expected_serial}, "
                    f"received {measures.serial_number}",
                    file=sys.stderr,
                )
                return 2
            config = await client.get_config()
            api_version = client.api_version
            updated_config = None
            if options.config_updates is not None:
                await _put_config(client, options.config_updates)
                updated_config = await client.get_config()
            if options.calibrate_co2:
                await client.request_co2_calibration()
            if options.test_leds:
                await client.request_led_bar_test()
    except AirGradientError as err:
        print(f"AirGradient request failed: {err}", file=sys.stderr)
        return 1

    print(f"Host: {options.host}")
    print(f"Detected API: {api_version.name if api_version is not None else 'unknown'}")
    _print_model("Measures", measures)
    _print_model("Config", config)
    if updated_config is not None:
        _print_model("Config after admitted PUT", updated_config)
    if options.calibrate_co2:
        print("CO2 calibration request admitted")
    if options.test_leds:
        print("LED test request admitted")
    return 0


def main() -> int:
    """Run the Local API reader."""
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
