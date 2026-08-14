"""Public parsers for versioned AirGradient Local API payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mashumaro import MissingField

from .exceptions import AirGradientParseError
from .models import (
    ApiVersion,
    Config,
    Measures,
    _parse_legacy_config,
    _parse_legacy_measures,
    _parse_v1_config,
    _parse_v1_measures,
)

if TYPE_CHECKING:
    from collections.abc import Callable


_ModelT = TypeVar("_ModelT")
_JsonData = str | bytes | bytearray
_MEASURES_PARSERS: dict[ApiVersion, Callable[[_JsonData], Measures]] = {
    ApiVersion.LEGACY: _parse_legacy_measures,
    ApiVersion.V1: _parse_v1_measures,
}
_CONFIG_PARSERS: dict[ApiVersion, Callable[[_JsonData], Config]] = {
    ApiVersion.LEGACY: _parse_legacy_config,
    ApiVersion.V1: _parse_v1_config,
}


def _parse_json(data: _JsonData, parser: Callable[[_JsonData], _ModelT]) -> _ModelT:
    """Parse a versioned payload into a normalized public model."""
    try:
        return parser(data)
    except (KeyError, MissingField, TypeError, ValueError) as err:
        msg = "Unable to parse AirGradient response"
        raise AirGradientParseError(msg) from err


def parse_measures_json(data: _JsonData, *, api_version: ApiVersion) -> Measures:
    """Deserialize measures using the selected Local API wire format."""
    return _parse_json(data, _MEASURES_PARSERS[api_version])


def parse_config_json(data: _JsonData, *, api_version: ApiVersion) -> Config:
    """Deserialize config using the selected Local API wire format."""
    return _parse_json(data, _CONFIG_PARSERS[api_version])
