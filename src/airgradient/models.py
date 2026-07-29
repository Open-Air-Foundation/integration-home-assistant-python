"""Models for AirGradient."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass
class Measures(DataClassORJSONMixin):
    """Measures model."""

    signal_strength: int = field(metadata=field_options(alias="wifi"))
    serial_number: str = field(metadata=field_options(alias="serialno"))
    boot_time: int = field(metadata=field_options(alias="bootCount"))
    firmware_version: str = field(metadata=field_options(alias="firmware"))
    model: str = field(metadata=field_options(alias="model"))
    rco2: int | None = None
    pm01: int | None = None
    pm02: float | None = None
    raw_pm02: int | None = field(default=None, metadata=field_options(alias="pm02"))
    compensated_pm02: float | None = field(
        default=None, metadata=field_options(alias="pm02Compensated")
    )
    pm10: int | None = None
    total_volatile_organic_component_index: int | None = field(
        default=None, metadata=field_options(alias="tvocIndex")
    )
    raw_total_volatile_organic_component: float | None = field(
        default=None, metadata=field_options(alias="tvocRaw")
    )
    pm003_count: int | None = field(
        default=None, metadata=field_options(alias="pm003Count")
    )
    nitrogen_index: int | None = field(
        default=None, metadata=field_options(alias="noxIndex")
    )
    raw_nitrogen: float | None = field(
        default=None, metadata=field_options(alias="noxRaw")
    )
    ambient_temperature: float | None = field(
        default=None, metadata=field_options(alias="atmp")
    )
    raw_ambient_temperature: float | None = field(
        default=None, metadata=field_options(alias="atmp")
    )
    compensated_ambient_temperature: float | None = field(
        default=None, metadata=field_options(alias="atmpCompensated")
    )
    raw_relative_humidity: float | None = field(
        default=None, metadata=field_options(alias="rhum")
    )
    relative_humidity: float | None = field(
        default=None, metadata=field_options(alias="rhum")
    )
    compensated_relative_humidity: float | None = field(
        default=None, metadata=field_options(alias="rhumCompensated")
    )

    @classmethod
    def __post_deserialize__(cls, obj: Measures) -> Measures:
        """Post deserialize hook."""
        if obj.compensated_ambient_temperature is not None:
            obj.ambient_temperature = obj.compensated_ambient_temperature
        if obj.compensated_relative_humidity is not None:
            obj.relative_humidity = obj.compensated_relative_humidity
        if obj.compensated_pm02 is not None:
            obj.pm02 = obj.compensated_pm02
        return obj


class PmStandard(StrEnum):
    """PM standard model."""

    UGM3 = "ugm3"
    USAQI = "us-aqi"


class TemperatureUnit(StrEnum):
    """Temperature unit model."""

    CELSIUS = "c"
    FAHRENHEIT = "f"


class ConfigurationControl(StrEnum):
    """Configuration control model."""

    CLOUD = "cloud"
    LOCAL = "local"
    NOT_INITIALIZED = "both"


class LedBarMode(StrEnum):
    """LED bar mode."""

    OFF = "off"
    CO2 = "co2"
    PM = "pm"


@dataclass
class Config(DataClassORJSONMixin):
    """Config model."""

    country: str
    pm_standard: PmStandard = field(metadata=field_options(alias="pmStandard"))
    led_bar_mode: LedBarMode | None = field(metadata=field_options(alias="ledBarMode"))
    co2_automatic_baseline_calibration_days: int = field(
        metadata=field_options(alias="abcDays")
    )
    temperature_unit: TemperatureUnit = field(
        metadata=field_options(alias="temperatureUnit")
    )
    configuration_control: ConfigurationControl = field(
        metadata=field_options(alias="configurationControl")
    )
    post_data_to_airgradient: bool = field(
        metadata=field_options(alias="postDataToAirGradient")
    )
    led_bar_brightness: int = field(metadata=field_options(alias="ledBarBrightness"))
    display_brightness: int = field(metadata=field_options(alias="displayBrightness"))
    nox_learning_offset: int = field(metadata=field_options(alias="noxLearningOffset"))
    tvoc_learning_offset: int = field(
        metadata=field_options(alias="tvocLearningOffset")
    )


@dataclass
class VersionCheck(DataClassORJSONMixin):
    """Version check model."""

    target_version: str = field(metadata=field_options(alias="targetVersion"))
