"""
Formatting core utilities for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
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


def _format_significant(value: float, digits: int = 12) -> str:
    """Format *value* with up to *digits* significant figures while avoiding
    scientific notation when not required, and trimming redundant zeros."""
    if value == 0:
        return '0'

    formatted = f"{value:.{digits}g}"
    if 'e' in formatted or 'E' in formatted:
        return formatted.lower()
    if '.' in formatted:
        return strip_trailing_zeros(formatted)
    return formatted


def _format_scientific(value: float, digits: int = 12) -> str:
    if value == 0:
        return '0'

    sign = -1 if value < 0 else 1
    abs_val = abs(value)

    exp_int = int(math.floor(math.log10(abs_val)))
    mantissa = abs_val / (10 ** exp_int)

    # Round mantissa to requested precision while limiting floating error drift.
    mantissa = round(mantissa, digits - 1)

    # If rounding pushed mantissa over 10, normalise again.
    if mantissa >= 10:
        mantissa /= 10
        exp_int += 1

    # Snap mantissas that are extremely close to integers (e.g. 0.9999999999 → 1).
    nearest_int = round(mantissa)
    if math.isclose(mantissa, nearest_int, rel_tol=0.0, abs_tol=10 ** -(digits + 1)):
        mantissa = float(nearest_int)

    mantissa_str = f"{mantissa:.{digits - 1}g}"
    mantissa_str = strip_trailing_zeros(mantissa_str)

    if mantissa_str in {'10', '+10'}:
        mantissa_str = '1'
        exp_int += 1

    if mantissa_str in {'-10'}:
        mantissa_str = '-1'
        exp_int += 1

    if mantissa_str in {'', '0', '-0'}:
        mantissa_str = '0'

    if sign < 0 and mantissa_str not in {'0'} and mantissa_str[0] != '-':
        mantissa_str = '-' + mantissa_str

    return f"{mantissa_str}e{exp_int:+d}"


def format_engineering(value: float, thresholds: Tuple[float, float] = SCI_THRESHOLDS, force: bool = False) -> str:
    """Engineering-style scientific notation with exponent steps of 3.
    - When force=True, always return engineering form (except exact zero → '0').
    - Otherwise, use plain formatting within thresholds.
    """
    if value == 0:
        return '0'
    lo, hi = thresholds
    abs_val = abs(value)
    if force or abs_val >= hi or abs_val < lo:
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
    """Pick an SI prefix yielding a human-friendly mantissa (prefer 1..999)."""
    if value == 0:
        return '', 1.0

    def converted_mag(prefix_mult: float) -> float:
        return abs(value / prefix_mult)

    best = None
    for prefix, mult in SI_PREFIXES.items():
        conv = converted_mag(mult)
        if 1 <= conv < 1000:
            score = abs(conv - 1)  # closer to 1 is nicer (e.g., 1n vs 999p)
            if best is None or score < best[0]:
                best = (score, prefix, mult)
    if best is not None:
        return best[1], best[2]

    best = None
    for prefix, mult in SI_PREFIXES.items():
        conv = converted_mag(mult)
        if 0.1 <= conv <= 9999:
            score = abs(conv - 1)
            if best is None or score < best[0]:
                best = (score, prefix, mult)
    if best is not None:
        return best[1], best[2]

    # Fallback: no good candidates; default to base
    return '', 1.0


def format_si(value: float, target_prefix: Optional[str] = None) -> str:
    if value == 0:
        return '0'

    def _format_with_prefix(converted: float, prefix: str) -> str:
        nearest = round(converted)
        if math.isclose(converted, nearest, rel_tol=0.0, abs_tol=1e-6):
            return f"{int(nearest)}{prefix}"
        return f"{_format_significant(converted, digits=12)}{prefix}"

    if target_prefix is not None and target_prefix in SI_PREFIXES:
        converted = value / SI_PREFIXES[target_prefix]
        return _format_with_prefix(converted, target_prefix)

    prefix, mult = _best_si_for(value)
    converted = value / mult
    return _format_with_prefix(converted, prefix)


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
    if value == 0:
        return '0'
    if value < 1e-9:
        return strip_trailing_zeros(f"{value/1e-12:.9g}") + 'p'
    elif value < 1e-6:
        return strip_trailing_zeros(f"{value/1e-9:.9g}") + 'n'
    elif value < 1e-3:
        return strip_trailing_zeros(f"{value/1e-6:.9g}") + 'u'
    elif value < 1:
        return strip_trailing_zeros(f"{value/1e-3:.9g}") + 'm'
    elif value < 1000:
        return strip_trailing_zeros(f"{value:.9g}")
    else:
        return strip_trailing_zeros(f"{value/1e3:.9g}") + 'k'


def parse_reference_style(reference: str) -> Tuple[str, Optional[str]]:
    """Parse reference string to detect style: ('si', prefix) | ('sci', expstr) | ('decimal', None) | ('zero', None)."""
    ref = reference.strip()
    if not ref:
        return 'decimal', None
    if ref == '0':
        return 'zero', None
    si_match = re.search(r'^(?:\+)?(\d+(?:\.\d+)?)\s*([fpnumkMG])(?:s)?$', ref)
    if si_match:
        magnitude = si_match.group(1)
        try:
            if float(magnitude) == 0.0:
                return 'zero', None
        except ValueError:
            pass
        return 'si', si_match.group(2)
    sci_match = re.search(r'^(?:\+)?(\d+(?:\.\d+)?)\s*e\s*([+-]?\d+)$', ref, re.IGNORECASE)
    if sci_match:
        try:
            if float(ref) == 0.0:
                return 'zero', None
        except ValueError:
            pass
        return 'sci', sci_match.group(2)
    try:
        if float(ref) == 0.0:
            return 'zero', None
    except ValueError:
        pass
    return 'decimal', None


def format_like_reference(value: float, reference: str) -> str:
    style, aux = parse_reference_style(reference)
    if style == 'si' and aux:
        return format_si(value, target_prefix=aux)
    if style == 'sci':
        return _format_scientific(value)
    if style == 'zero':
        # No style to inherit; suggest something sensible
        return suggest_optimal(value)
    # Default: decimal with readability; if awkward, fallback
    s = f"{value:g}"
    if is_awkward_format(s):
        return suggest_better_si(value)
    return s


__all__ = [
    'SI_PREFIXES', 'SCI_THRESHOLDS', 'EPSILON',
    'strip_trailing_zeros', 'format_engineering', 'format_si', 'is_awkward_format',
    'suggest_better_si', 'suggest_optimal', 'parse_reference_style', 'format_like_reference',
]


class FormatService:
    """App-facing formatting service built on top of the utilities in this module."""
    def format_time(self, time_value: float, reference_point: object | None = None) -> str:
        """Format a time value, optionally mirroring a reference point's time_str style."""
        if reference_point and hasattr(reference_point, 'time_str'):
            return format_like_reference(time_value, getattr(reference_point, 'time_str'))
        return suggest_optimal(time_value)

    def format_value(self, value: float, reference_point: object | None = None) -> str:
        """Format a value (unit-agnostic), optionally mirroring a reference point's value_str style."""
        if reference_point and hasattr(reference_point, 'value_str'):
            return format_like_reference(value, getattr(reference_point, 'value_str'))
        return suggest_optimal(value)

    # Convenience wrappers used elsewhere in the app
    def format_si(self, value: float) -> str:
        return format_si(value)

    def format_engineering(self, value: float) -> str:
        return format_engineering(value)

