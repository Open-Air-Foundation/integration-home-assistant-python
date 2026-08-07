"""Tests for the util module."""

from __future__ import annotations

import pytest

from airgradient import get_model_name


@pytest.mark.parametrize(
    ("model_id", "model_name"),
    [
        ("I-9PSL", "AirGradient ONE"),
        ("I-9PSL-DE", "AirGradient ONE"),
        ("O-1PPT", "AirGradient Open Air"),
        ("O-1PST", "AirGradient Open Air"),
        ("P-1PSG", "AirGradient Go"),
        ("P-1PSG-TEST", "AirGradient Go"),
        ("DIY-PRO-4.3", "AirGradient DIY"),
        ("DIY-PRO-3.7", "AirGradient DIY"),
        ("DIY-BASIC-4.0", "AirGradient DIY"),
        ("ABC", None),
    ],
)
def test_get_model_name(model_id: str, model_name: str | None) -> None:
    """Test get_model_name."""
    assert get_model_name(model_id) == model_name
