"""Tests for public versioned JSON parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from airgradient import (
    AirGradientParseError,
    ApiVersion,
    Config,
    Corrections,
    Measures,
    PmStandard,
    parse_config_json,
    parse_measures_json,
)
from tests import load_fixture

if TYPE_CHECKING:
    from collections.abc import Callable


def test_public_models_are_plain_dataclasses() -> None:
    """Test that normalized models do not expose wire serialization methods."""
    assert not hasattr(Measures, "from_json")
    assert not hasattr(Config, "from_json")
    assert not hasattr(Corrections, "from_json")


def test_parse_legacy_measures() -> None:
    """Test parsing legacy measures through the public parser."""
    measures = parse_measures_json(
        load_fixture("current_measures_zero.json"),
        api_version=ApiVersion.LEGACY,
    )
    assert measures.ambient_temperature == 0
    assert measures.relative_humidity == 0
    assert measures.pm02 == 0


def test_parse_legacy_boot_count_fallback() -> None:
    """Test parsing legacy bootCount through the public parser."""
    measures = parse_measures_json(
        load_fixture("legacy_boot_count_only.json"),
        api_version=ApiVersion.LEGACY,
    )
    assert measures.boot_time == 4


def test_parse_v1_measures() -> None:
    """Test parsing V1 measures through the public parser."""
    measures = parse_measures_json(
        load_fixture("v1/measures_full.json").encode(),
        api_version=ApiVersion.V1,
    )
    assert measures.model == "P-1PSG"
    assert measures.pm02 == 2.5
    assert measures.pm005_count == 90
    assert measures.raw_pm02 is None


def test_parse_legacy_config() -> None:
    """Test parsing legacy config through the public parser."""
    config = parse_config_json(
        load_fixture("config.json"),
        api_version=ApiVersion.LEGACY,
    )
    assert config.country == "DE"
    assert config.pm_standard is PmStandard.UGM3
    assert config.cloud_connection is None


def test_parse_v1_config() -> None:
    """Test parsing V1 config through the public parser."""
    config = parse_config_json(
        bytearray(load_fixture("v1/config_go.json").encode()),
        api_version=ApiVersion.V1,
    )
    assert config.country is None
    assert config.pm_standard is PmStandard.UGM3
    assert config.cloud_connection is True
    assert config.corrections is not None
    assert config.corrections.temperature is not None
    assert config.corrections.temperature.slr is not None
    assert config.corrections.temperature.slr.scaling_factor == 1.1


@pytest.mark.parametrize(
    ("parser", "payload"),
    [
        (parse_measures_json, "{}"),
        (parse_config_json, "{"),
    ],
)
def test_parser_errors(
    parser: Callable[..., Measures | Config],
    payload: str,
) -> None:
    """Test public parsing errors."""
    with pytest.raises(AirGradientParseError):
        parser(payload, api_version=ApiVersion.LEGACY)
