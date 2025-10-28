"""Waveform generator modules for PWL Editor."""

from .square import (
    SquareWaveConfig,
    SquareWaveResult,
    SquareWaveValidationError,
    generate_square_wave,
)
from .triangle import (
    TriangleWaveConfig,
    TriangleWaveResult,
    TriangleWaveValidationError,
    generate_triangle_wave,
)
from .saw import (
    SawWaveConfig,
    SawWaveResult,
    SawWaveValidationError,
    generate_saw_wave,
)

__all__ = [
    "SquareWaveConfig",
    "SquareWaveResult",
    "SquareWaveValidationError",
    "generate_square_wave",
    "TriangleWaveConfig",
    "TriangleWaveResult",
    "TriangleWaveValidationError",
    "generate_triangle_wave",
    "SawWaveConfig",
    "SawWaveResult",
    "SawWaveValidationError",
    "generate_saw_wave",
]
