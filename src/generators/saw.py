"""
Sawtooth waveform generator for the PWL Editor.
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


class SawWaveValidationError(ValueError):
    """Raised when a saw wave configuration cannot be generated."""


@dataclass(frozen=True)
class SawWaveConfig:
    """Parameter set for generating a saw waveform."""

    low_level: float
    high_level: float
    period: float
    ramp_fraction: float
    cycles: int
    start_time: float = 0.0
    edge_ppm: float = 5.0
    prefer_relative: bool = False


@dataclass(frozen=True)
class SawWaveResult:
    """Result bundle returned by :func:`generate_saw_wave`."""

    data: PwlData
    warnings: List[str]


def generate_saw_wave(
    config: SawWaveConfig,
    *,
    format_service: Optional[FormatService] = None,
) -> SawWaveResult:
    """Generate a saw waveform based on *config*."""

    errors = _validate_config(config)
    if errors:
        raise SawWaveValidationError("; ".join(errors))

    if format_service is None:
        format_service = FormatService()

    samples, meta = _generate_samples(config)
    data = _build_pwl_data(
        config=config,
        samples=samples,
        format_service=format_service,
    )

    warnings = _derive_warnings(config, meta)
    return SawWaveResult(data=data, warnings=warnings)


# ---------------------------------------------------------------------------
# Internal helpers


def _validate_config(config: SawWaveConfig) -> List[str]:
    errors: List[str] = []
    if config.period <= 0:
        errors.append("period must be positive")
    if not 0 < config.ramp_fraction <= 1:
        errors.append("ramp_fraction must be greater than 0 and at most 1")
    if config.cycles < 1:
        errors.append("cycles must be at least 1")
    if config.edge_ppm < 0:
        errors.append("edge_ppm must be non-negative")
    if config.start_time < 0:
        errors.append("start_time must be non-negative")
    return errors


def _generate_samples(config: SawWaveConfig) -> tuple[List[tuple[float, float]], Dict[str, float | bool]]:
    low = config.low_level
    high = config.high_level
    period = config.period
    amplitude_delta = high - low

    edge_fraction = max(config.edge_ppm, 0.0) * 1e-6
    requested_ramp_fraction = min(max(config.ramp_fraction, 1e-15), 1.0)
    max_ramp_fraction = 1.0
    if edge_fraction > 0 and not math.isclose(amplitude_delta, 0.0, abs_tol=1e-18):
        max_ramp_fraction = max(1.0 - edge_fraction, 0.0)

    if requested_ramp_fraction > max_ramp_fraction:
        ramp_fraction = max_ramp_fraction
        ramp_fraction_clamped = True
    else:
        ramp_fraction = requested_ramp_fraction
        ramp_fraction_clamped = False

    ramp_duration = period * ramp_fraction
    reset_budget = max(period - ramp_duration, 0.0)
    effective_edge = 0.0
    if reset_budget > 0 and edge_fraction > 0 and not math.isclose(amplitude_delta, 0.0, abs_tol=1e-18):
        effective_edge = min(edge_fraction * period, reset_budget)

    tail_duration = max(reset_budget - effective_edge, 0.0)

    samples: List[tuple[float, float]] = []
    _append_point(samples, config.start_time, low)

    for cycle in range(config.cycles):
        cycle_start = config.start_time + cycle * period
        _append_point(samples, cycle_start, low)

        if ramp_duration > 0 and not math.isclose(high, low, abs_tol=1e-15):
            _append_point(samples, cycle_start + ramp_duration, high)
        elif not math.isclose(high, low, abs_tol=1e-15):
            _append_point(samples, cycle_start, high)

        if reset_budget > 0:
            reset_start = cycle_start + ramp_duration
            if effective_edge > 0 and not math.isclose(high, low, abs_tol=1e-15):
                _append_point(samples, reset_start + effective_edge, low)
            elif not math.isclose(high, low, abs_tol=1e-15):
                _append_point(samples, reset_start, low)

            _append_point(samples, cycle_start + period, low)
        else:
            # Ramp occupies the full period; next cycle start will handle the reset.
            continue

    meta: Dict[str, float | bool] = {
        "ramp_fraction_effective": ramp_fraction,
        "requested_ramp_fraction": requested_ramp_fraction,
        "ramp_fraction_clamped": ramp_fraction_clamped,
        "edge_fraction": edge_fraction,
        "edge_duration": effective_edge,
        "reset_budget": reset_budget,
        "tail_duration": tail_duration,
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
    config: SawWaveConfig,
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


def _derive_warnings(config: SawWaveConfig, meta: Dict[str, float | bool]) -> List[str]:
    warnings: List[str] = []

    amplitude_delta = abs(meta.get("amplitude_delta", config.high_level - config.low_level))
    if amplitude_delta == 0:
        return warnings

    reset_budget = meta.get("reset_budget", 0.0)
    edge_fraction = meta.get("edge_fraction", 0.0)
    edge_duration = meta.get("edge_duration", 0.0)
    period = meta.get("period", config.period)

    if meta.get("ramp_fraction_clamped"):
        warnings.append("Ramp fraction reduced to leave time for reset edge.")

    if reset_budget <= 0:
        warnings.append("Reset interval collapsed; waveform stays at high level until cycle boundary.")
        return warnings

    if edge_fraction == 0:
        return warnings

    requested_edge = edge_fraction * period
    if edge_duration + 1e-15 < requested_edge:
        warnings.append("Reset edge duration limited by available reset interval.")

    return warnings


__all__ = [
    "SawWaveConfig",
    "SawWaveResult",
    "SawWaveValidationError",
    "generate_saw_wave",
]
