"""Public parsers for versioned AirGradient Local API payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mashumaro import MissingField

from ._wire_models import (
    parse_legacy_config,
    parse_legacy_measures,
    parse_v1_config,
    parse_v1_measures,
)
from .exceptions import AirGradientParseError
from .models import ApiVersion, Config, Measures

if TYPE_CHECKING:
    from collections.abc import Callable


_ModelT = TypeVar("_ModelT")
_JsonData = str | bytes | bytearray


def _parse_json(data: _JsonData, parser: Callable[[_JsonData], _ModelT]) -> _ModelT:
    """Parse a versioned payload into a normalized public model."""
    try:
        return parser(data)
    except (KeyError, MissingField, TypeError, ValueError) as err:
        msg = "Unable to parse AirGradient response"
        raise AirGradientParseError(msg) from err


def parse_measures_json(data: _JsonData, *, api_version: ApiVersion) -> Measures:
    """Deserialize measures using the selected Local API wire format."""
    parser = (
        parse_v1_measures if api_version is ApiVersion.V1 else parse_legacy_measures
    )
    return _parse_json(data, parser)


def parse_config_json(data: _JsonData, *, api_version: ApiVersion) -> Config:
    """Deserialize config using the selected Local API wire format."""
    parser = parse_v1_config if api_version is ApiVersion.V1 else parse_legacy_config
    return _parse_json(data, parser)
