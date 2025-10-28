"""
Triangle waveform generator for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from pwl_parser import PwlData, PwlPoint
from services.formatting import FormatService


class TriangleWaveValidationError(ValueError):
    """Raised when a triangle wave configuration cannot be generated."""


@dataclass(frozen=True)
class TriangleWaveConfig:
    """Parameter set for generating a triangle waveform."""

    low_level: float
    high_level: float
    period: float
    symmetry: float
    cycles: int
    start_time: float = 0.0
    prefer_relative: bool = False


@dataclass(frozen=True)
class TriangleWaveResult:
    """Result bundle returned by :func:`generate_triangle_wave`."""

    data: PwlData
    warnings: List[str]


def generate_triangle_wave(
    config: TriangleWaveConfig,
    *,
    format_service: Optional[FormatService] = None,
) -> TriangleWaveResult:
    """Generate a triangle waveform based on *config*."""

    errors = _validate_config(config)
    if errors:
        raise TriangleWaveValidationError("; ".join(errors))

    if format_service is None:
        format_service = FormatService()

    samples, meta = _generate_samples(config)
    data = _build_pwl_data(
        config=config,
        samples=samples,
        format_service=format_service,
    )

    warnings = _derive_warnings(config, meta)
    return TriangleWaveResult(data=data, warnings=warnings)


# ---------------------------------------------------------------------------
# Internal helpers


SYMMETRY_MIN = 1e-3
SYMMETRY_MAX = 1.0 - 1e-3


def _validate_config(config: TriangleWaveConfig) -> List[str]:
    errors: List[str] = []
    if config.period <= 0:
        errors.append("period must be positive")
    if not 0 <= config.symmetry <= 1:
        errors.append("symmetry must be between 0 and 1 (inclusive)")
    if config.cycles < 1:
        errors.append("cycles must be at least 1")
    if config.start_time < 0:
        errors.append("start_time must be non-negative")
    return errors


def _generate_samples(
    config: TriangleWaveConfig,
) -> tuple[List[tuple[float, float]], Dict[str, float | bool]]:
    low = config.low_level
    high = config.high_level
    period = config.period
    amplitude_delta = high - low

    requested_symmetry = config.symmetry
    clamped_symmetry = min(max(requested_symmetry, SYMMETRY_MIN), SYMMETRY_MAX)
    symmetry_adjusted = not math.isclose(clamped_symmetry, requested_symmetry, rel_tol=0.0, abs_tol=1e-12)

    symmetry_fraction = clamped_symmetry
    rise_duration = period * symmetry_fraction
    fall_duration = period - rise_duration

    samples: List[tuple[float, float]] = []
    _append_point(samples, config.start_time, low)

    for cycle in range(config.cycles):
        cycle_start = config.start_time + cycle * period
        _append_point(samples, cycle_start, low)

        if not math.isclose(high, low, abs_tol=1e-15):
            peak_time = cycle_start + rise_duration
            if rise_duration <= 0:
                _append_point(samples, cycle_start, high)
            else:
                _append_point(samples, peak_time, high)

            end_time = cycle_start + period
            if fall_duration <= 0:
                _append_point(samples, peak_time, low)
            else:
                _append_point(samples, end_time, low)
        else:
            end_time = cycle_start + period
            _append_point(samples, end_time, low)

    meta: Dict[str, float | bool] = {
        "symmetry_effective": symmetry_fraction,
        "requested_symmetry": requested_symmetry,
        "symmetry_clamped": symmetry_adjusted,
        "rise_duration": rise_duration,
        "fall_duration": fall_duration,
        "amplitude_delta": amplitude_delta,
        "period": period,
    }

    return samples, meta


def _append_point(samples: List[tuple[float, float]], time: float, value: float) -> None:
    """Append a point while maintaining monotonic timestamps."""

    if samples:
        last_time, last_value = samples[-1]
        if time < last_time:
            time = last_time
        if math.isclose(time, last_time, abs_tol=1e-15):
            time = last_time
            if math.isclose(value, last_value, abs_tol=1e-12):
                return
    samples.append((time, value))


def _build_pwl_data(
    *,
    config: TriangleWaveConfig,
    samples: Sequence[tuple[float, float]],
    format_service: FormatService,
) -> PwlData:
    data = PwlData()
    data.default_format = "relative" if config.prefer_relative else "absolute"

    points: List[PwlPoint] = []
    previous_time = 0.0

    for index, (absolute_time, value) in enumerate(samples):
        if index == 0 or not config.prefer_relative:
            time_str = format_service.format_time(absolute_time)
            is_relative = False
        else:
            delta = max(absolute_time - previous_time, 0.0)
            if config.prefer_relative and delta != 0.0:
                delta = float(f"{delta:.12g}")
            time_str = format_service.format_time(delta)
            is_relative = True

        value_ref = points[-1] if points else None
        value_str = format_service.format_value(value, value_ref)
        point = PwlPoint(time_str, value_str, is_relative=is_relative)
        points.append(point)
        previous_time = absolute_time

    data.points = points
    data._values_discrete = []
    data._timestamps_discrete = []
    data._discrete_dirty = True
    return data


def _derive_warnings(
    config: TriangleWaveConfig,
    meta: Dict[str, float | bool],
) -> List[str]:
    warnings: List[str] = []

    amplitude_delta = abs(meta.get("amplitude_delta", config.high_level - config.low_level))
    if amplitude_delta == 0:
        return warnings

    if meta.get("symmetry_clamped"):
        warnings.append("Symmetry adjusted to keep both ramps finite.")

    rise_duration = meta.get("rise_duration", 0.0)
    fall_duration = meta.get("fall_duration", 0.0)
    if rise_duration <= 0:
        warnings.append("Rise segment collapsed to a step.")
    if fall_duration <= 0:
        warnings.append("Fall segment collapsed to a step.")

    return warnings


__all__ = [
    "TriangleWaveConfig",
    "TriangleWaveResult",
    "TriangleWaveValidationError",
    "generate_triangle_wave",
    "SYMMETRY_MIN",
    "SYMMETRY_MAX",
]
