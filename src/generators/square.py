"""
Square waveform generator for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from pwl_parser import PwlData, PwlPoint
from services.formatting import FormatService


class SquareWaveValidationError(ValueError):
    """Raised when a square wave configuration cannot be generated."""


@dataclass(frozen=True)
class SquareWaveConfig:
    """Parameter set for generating a square waveform."""

    low_level: float
    high_level: float
    period: float
    duty_cycle: float
    cycles: int
    start_time: float = 0.0
    initial_state_high: bool = False
    edge_ppm: float = 5.0
    prefer_relative: bool = False


@dataclass(frozen=True)
class SquareWaveResult:
    """Result bundle returned by :func:`generate_square_wave`."""

    data: PwlData
    warnings: List[str]


def generate_square_wave(
    config: SquareWaveConfig,
    *,
    format_service: Optional[FormatService] = None,
) -> SquareWaveResult:
    """Generate a square waveform based on *config*.

    Args:
        config: Square wave parameters.
        format_service: Optional `FormatService` instance. A new one is created by
            default.

    Returns:
        SquareWaveResult containing the generated ``PwlData`` and any warnings.
    """

    errors = _validate_config(config)
    if errors:
        raise SquareWaveValidationError("; ".join(errors))

    if format_service is None:
        format_service = FormatService()

    amplitudes = _generate_samples(config)
    data = _build_pwl_data(
        config=config,
        samples=amplitudes,
        format_service=format_service,
    )

    warnings = _derive_warnings(config)
    return SquareWaveResult(data=data, warnings=warnings)


# ---------------------------------------------------------------------------
# Internal helpers


def _validate_config(config: SquareWaveConfig) -> List[str]:
    errors: List[str] = []
    if config.period <= 0:
        errors.append("period must be positive")
    if not 0 < config.duty_cycle < 100:
        errors.append("duty_cycle must be between 0 and 100 (exclusive)")
    if config.cycles < 1:
        errors.append("cycles must be at least 1")
    if config.edge_ppm < 0:
        errors.append("edge_ppm must be non-negative")
    if config.start_time < 0:
        errors.append("start_time must be non-negative")
    return errors


def _generate_samples(config: SquareWaveConfig) -> List[tuple[float, float]]:
    low = config.low_level
    high = config.high_level
    amplitude_delta = high - low

    period = config.period
    duty_fraction = config.duty_cycle / 100.0
    high_time = period * duty_fraction
    low_time = period - high_time

    edge_fraction = max(config.edge_ppm, 0.0) * 1e-6
    edge_duration = edge_fraction * period

    if amplitude_delta == 0 or edge_duration == 0:
        rise_duration = 0.0
        fall_duration = 0.0
    else:
        rise_duration = min(edge_duration, low_time)
        fall_duration = min(edge_duration, high_time)

    high_plateau = max(high_time - fall_duration, 0.0)
    low_plateau = max(low_time - rise_duration, 0.0)

    samples: List[tuple[float, float]] = []
    t = config.start_time
    current_value = high if config.initial_state_high else low
    samples.append((t, current_value))

    start_with_high = config.initial_state_high

    for _ in range(config.cycles):
        if start_with_high:
            # High stage first
            t, current_value = _append_stage(
                samples,
                t,
                high_plateau,
                fall_duration,
                current_value,
                high,
                low,
            )
            # Low stage second
            t, current_value = _append_stage(
                samples,
                t,
                low_plateau,
                rise_duration,
                current_value,
                low,
                high,
            )
        else:
            # Low stage first
            t, current_value = _append_stage(
                samples,
                t,
                low_plateau,
                rise_duration,
                current_value,
                low,
                high,
            )
            # High stage second
            t, current_value = _append_stage(
                samples,
                t,
                high_plateau,
                fall_duration,
                current_value,
                high,
                low,
            )

    return samples


def _append_stage(
    samples: List[tuple[float, float]],
    start_time: float,
    plateau_duration: float,
    ramp_duration: float,
    current_value: float,
    plateau_value: float,
    next_value: float,
) -> tuple[float, float]:
    """Append plateau and ramp segments for a stage."""

    t = start_time
    if plateau_duration > 0:
        t += plateau_duration
        if t > samples[-1][0] or plateau_value != samples[-1][1]:
            samples.append((t, plateau_value))
        current_value = plateau_value

    if ramp_duration > 0 and next_value != current_value:
        t += ramp_duration
        samples.append((t, next_value))
        current_value = next_value

    return t, current_value


def _build_pwl_data(
    *,
    config: SquareWaveConfig,
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


def _derive_warnings(config: SquareWaveConfig) -> List[str]:
    warnings: List[str] = []

    amplitude_delta = abs(config.high_level - config.low_level)
    if amplitude_delta == 0:
        return warnings

    period = config.period
    duty_fraction = config.duty_cycle / 100.0
    high_time = period * duty_fraction
    low_time = period - high_time

    edge_fraction = max(config.edge_ppm, 0.0) * 1e-6
    if edge_fraction == 0:
        return warnings

    edge_duration = edge_fraction * config.period
    if low_time > 0 and edge_duration > low_time + 1e-15:
        warnings.append("Rising edge duration limited by available low interval.")
    if high_time > 0 and edge_duration > high_time + 1e-15:
        warnings.append("Falling edge duration limited by available high interval.")

    return warnings


__all__ = [
    "SquareWaveConfig",
    "SquareWaveResult",
    "SquareWaveValidationError",
    "generate_square_wave",
]
