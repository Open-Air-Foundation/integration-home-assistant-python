"""Private wire-format models for AirGradient Local APIs."""

from __future__ import annotations

from dataclasses import dataclass, field

from mashumaro import field_options
from mashumaro.mixins.orjson import DataClassORJSONMixin

from .models import (
    Config,
    ConfigurationControl,
    CorrectionAlgorithm,
    Corrections,
    CorrectionSlr,
    GpsMode,
    HumidityCorrection,
    LedBarMode,
    Measures,
    Pm25Correction,
    Pm25CorrectionSlr,
    PmStandard,
    TemperatureCorrection,
    TemperatureUnit,
)


@dataclass
class _LegacyMeasures(DataClassORJSONMixin):
    """Legacy measures response."""

    serial_number: str = field(metadata=field_options(alias="serialno"))
    firmware_version: str = field(metadata=field_options(alias="firmware"))
    model: str
    boot: int | None = None
    boot_count: int | None = field(
        default=None, metadata=field_options(alias="bootCount")
    )
    signal_strength: int | None = field(
        default=None, metadata=field_options(alias="wifi")
    )
    rco2: int | None = None
    pm01: int | float | None = None
    pm02: int | float | None = None
    compensated_pm02: float | None = field(
        default=None, metadata=field_options(alias="pm02Compensated")
    )
    pm10: int | float | None = None
    tvoc_index: int | None = field(
        default=None, metadata=field_options(alias="tvocIndex")
    )
    tvoc_raw: float | None = field(
        default=None, metadata=field_options(alias="tvocRaw")
    )
    pm003_count: int | None = field(
        default=None, metadata=field_options(alias="pm003Count")
    )
    nox_index: int | None = field(
        default=None, metadata=field_options(alias="noxIndex")
    )
    nox_raw: float | None = field(default=None, metadata=field_options(alias="noxRaw"))
    temperature: float | None = field(
        default=None, metadata=field_options(alias="atmp")
    )
    compensated_temperature: float | None = field(
        default=None, metadata=field_options(alias="atmpCompensated")
    )
    humidity: float | None = field(default=None, metadata=field_options(alias="rhum"))
    compensated_humidity: float | None = field(
        default=None, metadata=field_options(alias="rhumCompensated")
    )

    def normalize(self) -> Measures:
        """Convert the legacy response to public normalized measures."""
        boot_time = self.boot if self.boot is not None else self.boot_count
        if boot_time is None:
            msg = "Legacy measures response is missing boot"
            raise ValueError(msg)
        return Measures(
            serial_number=self.serial_number,
            boot_time=boot_time,
            firmware_version=self.firmware_version,
            model=self.model,
            signal_strength=self.signal_strength,
            rco2=self.rco2,
            pm01=self.pm01,
            pm02=(
                self.compensated_pm02
                if self.compensated_pm02 is not None
                else float(self.pm02)
                if self.pm02 is not None
                else None
            ),
            raw_pm02=self.pm02,
            compensated_pm02=self.compensated_pm02,
            pm10=self.pm10,
            total_volatile_organic_component_index=self.tvoc_index,
            raw_total_volatile_organic_component=self.tvoc_raw,
            pm003_count=self.pm003_count,
            nitrogen_index=self.nox_index,
            raw_nitrogen=self.nox_raw,
            ambient_temperature=(
                self.compensated_temperature
                if self.compensated_temperature is not None
                else self.temperature
            ),
            raw_ambient_temperature=self.temperature,
            compensated_ambient_temperature=self.compensated_temperature,
            raw_relative_humidity=self.humidity,
            relative_humidity=(
                self.compensated_humidity
                if self.compensated_humidity is not None
                else self.humidity
            ),
            compensated_relative_humidity=self.compensated_humidity,
        )


@dataclass
class _V1Measures(DataClassORJSONMixin):
    """Local API V1 measures response."""

    serial_number: str = field(metadata=field_options(alias="serialNumber"))
    model: str
    firmware_version: str = field(metadata=field_options(alias="firmware"))
    boot_time: int = field(metadata=field_options(alias="boot"))
    signal_strength: int | None = field(
        default=None, metadata=field_options(alias="wifiRssi")
    )
    co2: int | None = None
    pm01: int | float | None = None
    pm25: int | float | None = None
    pm10: int | float | None = None
    pm003_count: int | None = field(
        default=None, metadata=field_options(alias="pm003Count")
    )
    pm005_count: int | None = field(
        default=None, metadata=field_options(alias="pm005Count")
    )
    pm01_count: int | None = field(
        default=None, metadata=field_options(alias="pm01Count")
    )
    pm02_count: int | None = field(
        default=None, metadata=field_options(alias="pm02Count")
    )
    pm50_count: int | None = field(
        default=None, metadata=field_options(alias="pm50Count")
    )
    pm10_count: int | None = field(
        default=None, metadata=field_options(alias="pm10Count")
    )
    temperature: float | None = field(
        default=None, metadata=field_options(alias="temperature")
    )
    humidity: float | None = None
    tvoc_index: int | None = field(
        default=None, metadata=field_options(alias="tvocIndex")
    )
    tvoc_raw: int | None = field(default=None, metadata=field_options(alias="tvocRaw"))
    nox_index: int | None = field(
        default=None, metadata=field_options(alias="noxIndex")
    )
    nox_raw: int | None = field(default=None, metadata=field_options(alias="noxRaw"))
    battery_percentage: int | None = field(
        default=None, metadata=field_options(alias="battPercent")
    )
    battery_voltage: float | None = field(
        default=None, metadata=field_options(alias="battVolt")
    )
    charge_voltage: float | None = field(
        default=None, metadata=field_options(alias="chargeVolt")
    )

    def normalize(self) -> Measures:
        """Convert the V1 response to public normalized measures."""
        return Measures(
            serial_number=self.serial_number,
            boot_time=self.boot_time,
            firmware_version=self.firmware_version,
            model=self.model,
            signal_strength=self.signal_strength,
            rco2=self.co2,
            pm01=self.pm01,
            pm02=self.pm25,
            pm10=self.pm10,
            total_volatile_organic_component_index=self.tvoc_index,
            raw_total_volatile_organic_component=self.tvoc_raw,
            pm003_count=self.pm003_count,
            nitrogen_index=self.nox_index,
            raw_nitrogen=self.nox_raw,
            ambient_temperature=self.temperature,
            relative_humidity=self.humidity,
            pm005_count=self.pm005_count,
            pm01_count=self.pm01_count,
            pm02_count=self.pm02_count,
            pm50_count=self.pm50_count,
            pm10_count=self.pm10_count,
            battery_percentage=self.battery_percentage,
            battery_voltage=self.battery_voltage,
            charge_voltage=self.charge_voltage,
        )


@dataclass
class _LegacyConfig(DataClassORJSONMixin):
    """Legacy config response."""

    country: str
    pm_standard: PmStandard = field(metadata=field_options(alias="pmStandard"))
    led_bar_mode: LedBarMode = field(metadata=field_options(alias="ledBarMode"))
    abc_days: int = field(metadata=field_options(alias="abcDays"))
    temperature_unit: TemperatureUnit = field(
        metadata=field_options(alias="temperatureUnit")
    )
    configuration_control: ConfigurationControl = field(
        metadata=field_options(alias="configurationControl")
    )
    post_data: bool = field(metadata=field_options(alias="postDataToAirGradient"))
    led_bar_brightness: int = field(metadata=field_options(alias="ledBarBrightness"))
    display_brightness: int = field(metadata=field_options(alias="displayBrightness"))
    nox_learning_offset: int = field(metadata=field_options(alias="noxLearningOffset"))
    tvoc_learning_offset: int = field(
        metadata=field_options(alias="tvocLearningOffset")
    )

    def normalize(self) -> Config:
        """Convert the legacy response to public normalized config."""
        return Config(
            country=self.country,
            pm_standard=self.pm_standard,
            led_bar_mode=self.led_bar_mode,
            co2_automatic_baseline_calibration_days=self.abc_days,
            temperature_unit=self.temperature_unit,
            configuration_control=self.configuration_control,
            post_data_to_airgradient=self.post_data,
            led_bar_brightness=self.led_bar_brightness,
            display_brightness=self.display_brightness,
            nox_learning_offset=self.nox_learning_offset,
            tvoc_learning_offset=self.tvoc_learning_offset,
        )


@dataclass
class _CorrectionSlr:
    """V1 linear correction parameters."""

    intercept: float
    scaling_factor: float = field(metadata=field_options(alias="scalingFactor"))

    def normalize(self) -> CorrectionSlr:
        """Convert to normalized linear correction parameters."""
        return CorrectionSlr(
            intercept=self.intercept,
            scaling_factor=self.scaling_factor,
        )


@dataclass
class _Pm25CorrectionSlr(_CorrectionSlr):
    """V1 PM2.5 linear correction parameters."""

    use_epa_2021: bool = field(metadata=field_options(alias="useEpa2021"))

    def normalize(self) -> Pm25CorrectionSlr:
        """Convert to normalized PM2.5 correction parameters."""
        return Pm25CorrectionSlr(
            intercept=self.intercept,
            scaling_factor=self.scaling_factor,
            use_epa_2021=self.use_epa_2021,
        )


@dataclass
class _Pm25Correction:
    """V1 PM2.5 correction settings."""

    correction_algorithm: CorrectionAlgorithm = field(
        metadata=field_options(alias="correctionAlgorithm")
    )
    slr: _Pm25CorrectionSlr | None

    def normalize(self) -> Pm25Correction:
        """Convert to normalized PM2.5 correction settings."""
        return Pm25Correction(
            correction_algorithm=self.correction_algorithm,
            slr=self.slr.normalize() if self.slr is not None else None,
        )


@dataclass
class _TemperatureCorrection:
    """V1 temperature correction settings."""

    correction_algorithm: CorrectionAlgorithm = field(
        metadata=field_options(alias="correctionAlgorithm")
    )
    slr: _CorrectionSlr | None

    def normalize(self) -> TemperatureCorrection:
        """Convert to normalized temperature correction settings."""
        return TemperatureCorrection(
            correction_algorithm=self.correction_algorithm,
            slr=self.slr.normalize() if self.slr is not None else None,
        )


@dataclass
class _HumidityCorrection:
    """V1 humidity correction settings."""

    correction_algorithm: CorrectionAlgorithm = field(
        metadata=field_options(alias="correctionAlgorithm")
    )
    slr: _CorrectionSlr | None

    def normalize(self) -> HumidityCorrection:
        """Convert to normalized humidity correction settings."""
        return HumidityCorrection(
            correction_algorithm=self.correction_algorithm,
            slr=self.slr.normalize() if self.slr is not None else None,
        )


@dataclass
class _Corrections:
    """V1 measurement correction settings."""

    pm25: _Pm25Correction | None = None
    temperature: _TemperatureCorrection | None = field(
        default=None, metadata=field_options(alias="temperature")
    )
    humidity: _HumidityCorrection | None = None

    def normalize(self) -> Corrections:
        """Convert to normalized measurement correction settings."""
        return Corrections(
            pm25=self.pm25.normalize() if self.pm25 is not None else None,
            temperature=(
                self.temperature.normalize() if self.temperature is not None else None
            ),
            humidity=(self.humidity.normalize() if self.humidity is not None else None),
        )


@dataclass
class _V1Config(DataClassORJSONMixin):
    """Local API V1 config response."""

    country: str | None = None
    pm_standard: PmStandard | None = field(
        default=None, metadata=field_options(alias="pmStandard")
    )
    led_bar_mode: LedBarMode | None = field(
        default=None, metadata=field_options(alias="ledMode")
    )
    abc_days: int | None = field(
        default=None, metadata=field_options(alias="co2AbcDays")
    )
    temperature_unit: TemperatureUnit | None = field(
        default=None, metadata=field_options(alias="temperatureUnit")
    )
    configuration_control: ConfigurationControl | None = field(
        default=None, metadata=field_options(alias="configurationControl")
    )
    post_data: bool | None = field(
        default=None, metadata=field_options(alias="postDataToCloud")
    )
    led_bar_brightness: int | None = field(
        default=None, metadata=field_options(alias="ledBarBrightness")
    )
    display_brightness: int | None = field(
        default=None, metadata=field_options(alias="displayBrightness")
    )
    nox_learning_offset: int | None = field(
        default=None, metadata=field_options(alias="noxLearningOffset")
    )
    tvoc_learning_offset: int | None = field(
        default=None, metadata=field_options(alias="tvocLearningOffset")
    )
    cloud_connection: bool | None = field(
        default=None, metadata=field_options(alias="cloudConnection")
    )
    measurement_interval: int | None = field(
        default=None, metadata=field_options(alias="measurementInterval")
    )
    gps_mode: GpsMode | None = field(
        default=None, metadata=field_options(alias="gpsMode")
    )
    gps_interval: int | None = field(
        default=None, metadata=field_options(alias="gpsInterval")
    )
    front_led_brightness: int | None = field(
        default=None, metadata=field_options(alias="frontLedBrightness")
    )
    back_led_brightness: int | None = field(
        default=None, metadata=field_options(alias="backLedBrightness")
    )
    touch_led_intensity: int | None = field(
        default=None, metadata=field_options(alias="touchLedIntensity")
    )
    buzzer_enabled: bool | None = field(
        default=None, metadata=field_options(alias="buzzerEnabled")
    )
    corrections: _Corrections | None = None

    def normalize(self) -> Config:
        """Convert the V1 response to public normalized config."""
        return Config(
            country=self.country,
            pm_standard=self.pm_standard,
            led_bar_mode=self.led_bar_mode,
            co2_automatic_baseline_calibration_days=self.abc_days,
            temperature_unit=self.temperature_unit,
            configuration_control=self.configuration_control,
            post_data_to_airgradient=self.post_data,
            led_bar_brightness=self.led_bar_brightness,
            display_brightness=self.display_brightness,
            nox_learning_offset=self.nox_learning_offset,
            tvoc_learning_offset=self.tvoc_learning_offset,
            cloud_connection=self.cloud_connection,
            measurement_interval=self.measurement_interval,
            gps_mode=self.gps_mode,
            gps_interval=self.gps_interval,
            front_led_brightness=self.front_led_brightness,
            back_led_brightness=self.back_led_brightness,
            touch_led_intensity=self.touch_led_intensity,
            buzzer_enabled=self.buzzer_enabled,
            corrections=(
                self.corrections.normalize() if self.corrections is not None else None
            ),
        )


def parse_legacy_measures(body: str | bytes | bytearray) -> Measures:
    """Parse and normalize a legacy measures response."""
    return _LegacyMeasures.from_json(body).normalize()


def parse_v1_measures(body: str | bytes | bytearray) -> Measures:
    """Parse and normalize a V1 measures response."""
    return _V1Measures.from_json(body).normalize()


def parse_legacy_config(body: str | bytes | bytearray) -> Config:
    """Parse and normalize a legacy config response."""
    return _LegacyConfig.from_json(body).normalize()


def parse_v1_config(body: str | bytes | bytearray) -> Config:
    """Parse and normalize a V1 config response."""
    return _V1Config.from_json(body).normalize()
