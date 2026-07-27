"""Utility functions for AirGradient."""

from __future__ import annotations


def get_model_name(model_id: str) -> str | None:
    """Get model name from identifier."""
    if model_id.startswith("I-9PSL"):
        return "AirGradient ONE"
    if model_id.startswith("O-1"):
        return "AirGradient Open Air"
    if model_id.startswith("P-1PSG"):
        return "AirGradient Go"
    if "DIY" in model_id:
        return "AirGradient DIY"
    return None
