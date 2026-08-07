"""Public models for AirGradient."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin


class ApiVersion(IntEnum):
    """AirGradient Local API version."""

    LEGACY = 0
    V1 = 1


@dataclass
class Measures:
    """Measures model."""

    signal_strength: int | None
    serial_number: str
    boot_time: int
    firmware_version: str
    model: str
    rco2: int | None = None
    pm01: int | float | None = None
    pm02: float | None = None
    raw_pm02: int | float | None = None
    compensated_pm02: float | None = None
    pm10: int | float | None = None
    total_volatile_organic_component_index: int | None = None
    raw_total_volatile_organic_component: float | None = None
    pm003_count: int | None = None
    nitrogen_index: int | None = None
    raw_nitrogen: float | None = None
    ambient_temperature: float | None = None
    raw_ambient_temperature: float | None = None
    compensated_ambient_temperature: float | None = None
    raw_relative_humidity: float | None = None
    relative_humidity: float | None = None
    compensated_relative_humidity: float | None = None
    pm005_count: int | None = None
    pm01_count: int | None = None
    pm02_count: int | None = None
    pm50_count: int | None = None
    pm10_count: int | None = None
    battery_percentage: int | None = None
    battery_voltage: float | None = None
    charge_voltage: float | None = None


class PmStandard(StrEnum):
    """PM standard model."""

    UGM3 = "ugm3"
    USAQI = "us-aqi"


class TemperatureUnit(StrEnum):
    """Temperature unit model."""

    CELSIUS = "c"
    FAHRENHEIT = "f"


class GpsMode(StrEnum):
    """GPS operating mode."""

    OFF = "off"
    TRACKING = "tracking"
    ALWAYS = "always"


class ConfigurationControl(StrEnum):
    """Configuration control model."""

    CLOUD = "cloud"
    LOCAL = "local"
    BOTH = "both"
    NOT_INITIALIZED = BOTH


class LedBarMode(StrEnum):
    """LED bar mode."""

    OFF = "off"
    CO2 = "co2"
    PM = "pm"


class CorrectionAlgorithm(StrEnum):
    """Measurement correction algorithm."""

    NONE = "none"
    EPA_2021 = "epa_2021"
    CUSTOM_VIA_PM25_RAW = "custom_via_pm25_raw"
    CUSTOM = "custom"


@dataclass
class CorrectionSlr:
    """Linear correction parameters."""

    intercept: float
    scaling_factor: float


@dataclass
class Pm25CorrectionSlr(CorrectionSlr):
    """PM2.5 linear correction parameters."""

    use_epa_2021: bool


@dataclass
class Pm25Correction:
    """PM2.5 correction settings."""

    correction_algorithm: CorrectionAlgorithm
    slr: Pm25CorrectionSlr | None


@dataclass
class TemperatureCorrection:
    """Temperature correction settings."""

    correction_algorithm: CorrectionAlgorithm
    slr: CorrectionSlr | None


@dataclass
class HumidityCorrection:
    """Humidity correction settings."""

    correction_algorithm: CorrectionAlgorithm
    slr: CorrectionSlr | None


@dataclass
class Corrections:
    """Supported measurement corrections."""

    pm25: Pm25Correction | None = None
    temperature: TemperatureCorrection | None = None
    humidity: HumidityCorrection | None = None


@dataclass
class Config:
    """Config model."""

    country: str | None = None
    pm_standard: PmStandard | None = None
    led_bar_mode: LedBarMode | None = None
    co2_automatic_baseline_calibration_days: int | None = None
    temperature_unit: TemperatureUnit | None = None
    configuration_control: ConfigurationControl | None = None
    post_data_to_airgradient: bool | None = None
    led_bar_brightness: int | None = None
    display_brightness: int | None = None
    nox_learning_offset: int | None = None
    tvoc_learning_offset: int | None = None
    cloud_connection: bool | None = None
    measurement_interval: int | None = None
    gps_mode: GpsMode | None = None
    front_led_brightness: int | None = None
    back_led_brightness: int | None = None
    touch_led_intensity: int | None = None
    buzzer_enabled: bool | None = None
    corrections: Corrections | None = None


@dataclass
class VersionCheck(DataClassORJSONMixin):
    """Version check model."""

    target_version: str = field(metadata=field_options(alias="targetVersion"))
