"""
PWL Editor - Shared Formatting Utilities
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic) - Code development and architecture
License: GPL-3.0-or-later

Provides:
- SI/engineering number formatting
- Reference-style preserving formatting (SI/scientific/decimal)
- Readability helpers (awkward detection, trailing zero trimming)

This module is intentionally free of project-specific types.
"""

from __future__ import annotations

import math
import re
from typing import Optional, Tuple

# Unified SI prefix map (include femto for GUI conversions)
SI_PREFIXES = {
    'f': 1e-15,
    'p': 1e-12,
    'n': 1e-9,
    'u': 1e-6,
    'm': 1e-3,
    '': 1.0,
    'k': 1e3,
    'M': 1e6,
    'G': 1e9,
}

# Scientific notation thresholds (inclusive ranges outside which we use engineering)
SCI_THRESHOLDS: Tuple[float, float] = (1e-4, 1e4)
EPSILON = 1e-10


def strip_trailing_zeros(s: str) -> str:
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def format_engineering(value: float, thresholds: Tuple[float, float] = SCI_THRESHOLDS) -> str:
    """Engineering-style scientific notation with exponent steps of 3, similar to existing behavior.
    Uses plain formatting for values within thresholds.
    """
    if value == 0:
        return '0'
    lo, hi = thresholds
    abs_val = abs(value)
    if abs_val >= hi or abs_val < lo:
        exponent = math.floor(math.log10(abs_val))
        stepped_exp = (exponent // 3) * 3
        mantissa = value / (10 ** stepped_exp)
        if abs(mantissa - round(mantissa)) < EPSILON:
            mantissa_str = str(int(round(mantissa)))
        else:
            mantissa_str = f"{mantissa:g}"
        return mantissa_str if stepped_exp == 0 else f"{mantissa_str}e{stepped_exp}"
    # Regular formatting within thresholds
    return strip_trailing_zeros(f"{value:.9g}")


def _best_si_for(value: float) -> Tuple[str, float]:
    """Pick an SI prefix yielding a human-friendly magnitude."""
    # Prefer magnitudes roughly 0.1 .. 9999
    candidates = []
    for prefix, mult in SI_PREFIXES.items():
        converted = value / mult
        if 0.1 <= abs(converted) <= 9999:
            candidates.append((prefix, abs(abs(converted) - 1000)))
    if not candidates:
        # Fallback: choose closest power-of-1000 prefix
        if value == 0:
            return '', 1.0
        exp = int(math.floor(math.log10(abs(value)) / 3)) * 3
        # map exp back to a known prefix if possible
        for p, m in SI_PREFIXES.items():
            if abs(math.log10(m) - exp) < 1e-9:
                return p, m
        return '', 1.0
    # Choose candidate whose converted magnitude is closest to 1000 (middle of range)
    prefix = min(candidates, key=lambda x: x[1])[0]
    return prefix, SI_PREFIXES[prefix]


def format_si(value: float, target_prefix: Optional[str] = None) -> str:
    if value == 0:
        return '0'
    if target_prefix is not None and target_prefix in SI_PREFIXES:
        converted = value / SI_PREFIXES[target_prefix]
        if abs(converted - round(converted)) < EPSILON:
            return f"{int(round(converted))}{target_prefix}"
        return f"{converted:g}{target_prefix}"
    # choose the best prefix
    prefix, mult = _best_si_for(value)
    converted = value / mult
    if abs(converted - round(converted)) < EPSILON:
        return f"{int(round(converted))}{prefix}"
    return f"{converted:g}{prefix}"


def is_awkward_format(s: str) -> bool:
    s = s.strip()
    # Very large SI mantissas like 500010n (prefer switching prefix)
    si_match = re.search(r'^(?:\+)?(\d+(?:\.\d+)?)\s*([fpnumkMG])(?:s)?$', s)
    if si_match:
        try:
            magnitude = float(si_match.group(1))
            if magnitude >= 10000:
                return True
        except ValueError:
            pass
    # Very long non-scientific decimals: count only digits; ignore 'e' formats
    if '.' in s and 'e' not in s.lower():
        digit_count = len(re.sub(r'[^0-9]', '', s))
        if digit_count > 8:
            return True
    return False


def suggest_better_si(value: float) -> str:
    """Suggest a more readable SI format when a reference-like formatting is awkward."""
    return format_si(value)


def suggest_optimal(value: float) -> str:
    """Suggest a user-friendly format for any positive value, mimicking existing behavior."""
    if value < 0:
        return '-' + suggest_optimal(-value)
    if value < 1e-9:
        return f"{value/1e-12:g}p"
    elif value < 1e-6:
        return f"{value/1e-9:g}n"
    elif value < 1e-3:
        return f"{value/1e-6:g}u"
    elif value < 1:
        return f"{value/1e-3:g}m"
    elif value < 1000:
        return f"{value:g}"
    else:
        return f"{value/1e3:g}k"


def parse_reference_style(reference: str) -> Tuple[str, Optional[str]]:
    """Parse reference string to detect style: ('si', prefix) | ('sci', expstr) | ('decimal', None) | ('zero', None)."""
    ref = reference.strip()
    if not ref:
        return 'decimal', None
    if ref == '0':
        return 'zero', None
    si_match = re.search(r'^(?:\+)?(\d+(?:\.\d+)?)\s*([fpnumkMG])(?:s)?$', ref)
    if si_match:
        return 'si', si_match.group(2)
    sci_match = re.search(r'^(?:\+)?(\d+(?:\.\d+)?)\s*e\s*([+-]?\d+)$', ref, re.IGNORECASE)
    if sci_match:
        return 'sci', sci_match.group(2)
    return 'decimal', None


def format_like_reference(value: float, reference: str) -> str:
    style, aux = parse_reference_style(reference)
    if style == 'si' and aux:
        return format_si(value, target_prefix=aux)
    if style == 'sci':
        return format_engineering(value)
    if style == 'zero':
        # No style to inherit; suggest something sensible
        return suggest_optimal(value)
    # Default: decimal with readability; if awkward, fallback
    s = f"{value:g}"
    if is_awkward_format(s):
        return suggest_better_si(value)
    return s
