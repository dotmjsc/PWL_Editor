"""
Waveform analysis and repair services for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, List, Optional, Sequence

from pwl_parser import PwlData, PwlPoint
from services.formatting import FormatService


@dataclass(frozen=True)
class DuplicateGroup:
    """Description of points that share an absolute timestamp."""

    indices: tuple[int, ...]
    timestamp: float

    def __post_init__(self):
        if len(self.indices) < 2:
            raise ValueError("DuplicateGroup requires at least two indices")


@dataclass(frozen=True)
class TimeReversal:
    """Description of consecutive points where time goes backwards."""

    first_index: int
    second_index: int
    time_before: float
    time_after: float

    def __post_init__(self):
        if self.second_index <= self.first_index:
            raise ValueError("second_index must be after first_index")


class WaveformAnalyzer:
    """Analyze a PwlData instance for structural waveform problems."""

    def __init__(self, pwl_data: PwlData, *, time_epsilon: float = 1e-15) -> None:
        self._pwl_data = pwl_data
        self._time_epsilon = max(time_epsilon, 0.0)

    @property
    def pwl_data(self) -> PwlData:
        return self._pwl_data

    def find_duplicate_timestamps(self) -> List[DuplicateGroup]:
        timestamps = self._pwl_data.timestamps
        if len(timestamps) < 2:
            return []

        groups: List[DuplicateGroup] = []
        current: List[int] = []

        for idx in range(1, len(timestamps)):
            if abs(timestamps[idx] - timestamps[idx - 1]) <= self._time_epsilon:
                if not current:
                    current = [idx - 1, idx]
                else:
                    current.append(idx)
            else:
                if current:
                    groups.append(DuplicateGroup(tuple(current), timestamps[current[0]]))
                    current = []
        if current:
            groups.append(DuplicateGroup(tuple(current), timestamps[current[0]]))
        return groups

    def find_time_reversals(self) -> List[TimeReversal]:
        timestamps = self._pwl_data.timestamps
        if len(timestamps) < 2:
            return []

        reversals: List[TimeReversal] = []
        for idx in range(len(timestamps) - 1):
            if timestamps[idx] > timestamps[idx + 1] + self._time_epsilon:
                reversals.append(
                    TimeReversal(
                        first_index=idx,
                        second_index=idx + 1,
                        time_before=timestamps[idx],
                        time_after=timestamps[idx + 1],
                    )
                )
        return reversals

    def find_all_issues(self) -> Dict[str, List]:
        issues: Dict[str, List] = {}
        duplicates = self.find_duplicate_timestamps()
        if duplicates:
            issues["duplicate_timestamps"] = duplicates
        reversals = self.find_time_reversals()
        if reversals:
            issues["time_reversals"] = reversals
        return issues


class WaveformRepairer:
    """Repair strategies for issues detected in PwlData waveforms."""

    _DUPLICATE_STRATEGIES = {"center", "shift_right", "shift_left", "remove", "none"}
    _DUPLICATE_ALIASES = {
        "distribute": "shift_right",
        "minimum_slew": "shift_right",
    }
    _REVERSAL_STRATEGIES = {"sort", "remove", "none"}
    _REVERSAL_ALIASES = {
        "leave": "none",
    }

    def __init__(self, pwl_data: PwlData, *, time_epsilon: float = 1e-15) -> None:
        self._source = pwl_data
        self._analyzer = WaveformAnalyzer(pwl_data, time_epsilon=time_epsilon)
        self._format_service = FormatService()
        self._time_epsilon = max(time_epsilon, 0.0)

    @property
    def analyzer(self) -> WaveformAnalyzer:
        return self._analyzer

    def repair_duplicates(
        self,
        max_slew_rate: float,
        *,
        time_tolerance: float = 1e-12,
        strategy: str = "center",
    ) -> PwlData:
        if max_slew_rate <= 0:
            raise ValueError("max_slew_rate must be positive")
        if time_tolerance <= 0:
            raise ValueError("time_tolerance must be positive")

        normalized_strategy = self._normalize_duplicate_strategy(strategy)
        if normalized_strategy not in self._DUPLICATE_STRATEGIES:
            raise ValueError(f"Unsupported duplicate strategy: {strategy}")
        if normalized_strategy == "none":
            return self._source

        groups = self._analyzer.find_duplicate_timestamps()
        if not groups:
            return self._source

        timestamps = list(self._source.timestamps)
        values = self._source.values

        if normalized_strategy == "remove":
            indices_to_remove = {
                idx for group in groups for idx in group.indices[1:]
            }
            filtered_points = [p for i, p in enumerate(self._source.points) if i not in indices_to_remove]
            filtered_times = [t for i, t in enumerate(timestamps) if i not in indices_to_remove]
            return self._rebuild_data(filtered_points, filtered_times)

        for group in groups:
            self._spread_group(
                timestamps,
                values,
                group,
                max_slew_rate=max_slew_rate,
                time_tolerance=time_tolerance,
                strategy=normalized_strategy,
            )

        return self._rebuild_data(self._source.points, timestamps)

    def repair_time_reversals(self, *, strategy: str = "sort") -> PwlData:
        normalized_strategy = self._normalize_reversal_strategy(strategy)
        if normalized_strategy not in self._REVERSAL_STRATEGIES:
            raise ValueError(f"Unsupported reversal strategy: {strategy}")
        if normalized_strategy == "none":
            return self._source

        reversals = self._analyzer.find_time_reversals()
        if not reversals:
            return self._source

        timestamps = list(self._source.timestamps)
        points = list(self._source.points)

        if normalized_strategy == "remove":
            indices_to_remove = {rev.second_index for rev in reversals}
            filtered_points = [p for i, p in enumerate(points) if i not in indices_to_remove]
            filtered_times = [t for i, t in enumerate(timestamps) if i not in indices_to_remove]
            return self._rebuild_data(filtered_points, filtered_times)

        sorted_pairs = sorted(((t, i) for i, t in enumerate(timestamps)), key=lambda item: item[0])
        reordered_points = [points[i] for _, i in sorted_pairs]
        reordered_times = [t for t, _ in sorted_pairs]
        return self._rebuild_data(reordered_points, reordered_times)

    # --- Internal helpers -------------------------------------------------

    def _spread_group(
        self,
        timestamps: List[float],
        values: Sequence[float],
        group: DuplicateGroup,
        *,
        max_slew_rate: float,
        time_tolerance: float,
        strategy: str,
    ) -> None:
        indices = group.indices
        if len(indices) < 2:
            return

        start_idx = indices[0]
        end_idx = indices[-1]
        origin_time = timestamps[start_idx]
        previous_time = timestamps[start_idx - 1] if start_idx > 0 else timestamps[start_idx]
        next_time = timestamps[end_idx + 1] if end_idx + 1 < len(timestamps) else None

        group_values = [values[i] for i in indices]
        value_span = max(group_values) - min(group_values)
        slew_span = value_span / max_slew_rate if value_span else 0.0
        min_span = time_tolerance * (len(indices) - 1)
        target_span = max(slew_span, min_span)

        base_min_start: Optional[float] = (
            previous_time + time_tolerance if start_idx > 0 else None
        )
        if strategy in {"center", "shift_right"}:
            min_start: Optional[float] = (
                base_min_start if base_min_start is not None else origin_time
            )
        else:
            min_start = base_min_start
        max_end: Optional[float] = (
            next_time - time_tolerance if next_time is not None else None
        )

        if strategy == "shift_left":
            window_end = origin_time
            if max_end is not None:
                window_end = min(window_end, max_end)
            window_start = window_end - target_span
            if min_start is not None and window_start < min_start:
                window_start = min_start
                window_end = window_start + target_span
        elif strategy == "center":
            window_start = origin_time - target_span / 2
            window_end = window_start + target_span
            if min_start is not None and window_start < min_start:
                shift = min_start - window_start
                window_start += shift
                window_end += shift
            if max_end is not None and window_end > max_end:
                shift = window_end - max_end
                window_start -= shift
                window_end -= shift
        else:  # shift_right and legacy aliases
            window_start = origin_time
            if min_start is not None and window_start < min_start:
                window_start = min_start
            window_end = window_start + target_span
            if max_end is not None and window_end > max_end:
                window_end = max_end
                window_start = window_end - target_span

        if window_end <= window_start:
            window_end = window_start + min_span

        span = window_end - window_start
        if span < min_span:
            deficit = min_span - span
            if strategy == "shift_left":
                window_start -= deficit
            elif strategy == "shift_right":
                window_end += deficit
            else:  # center
                window_start -= deficit / 2
                window_end += deficit / 2
            span = min_span

        spacing = span / (len(indices) - 1)

        for offset, point_index in enumerate(indices):
            timestamps[point_index] = window_start + spacing * offset

    def _normalize_duplicate_strategy(self, strategy: str) -> str:
        normalized = (strategy or "").strip().lower()
        return self._DUPLICATE_ALIASES.get(normalized, normalized)

    def _normalize_reversal_strategy(self, strategy: str) -> str:
        normalized = (strategy or "").strip().lower()
        return self._REVERSAL_ALIASES.get(normalized, normalized)

    def _rebuild_data(
        self,
        points: Sequence[PwlPoint],
        absolute_times: Sequence[float],
    ) -> PwlData:
        if len(points) != len(absolute_times):
            raise ValueError("Point/time length mismatch during rebuild")

        new_data = PwlData()
        new_data.timestep = self._source.timestep
        new_data.default_format = self._source.default_format

        if not points:
            return new_data

        formatted_points: List[PwlPoint] = []
        previous_time = 0.0

        for idx, (point, abs_time) in enumerate(zip(points, absolute_times)):
            ref = SimpleNamespace(time_str=point.time_str)
            if idx == 0 or not point.is_relative:
                time_value = abs_time
                time_str = self._format_service.format_time(time_value, ref)
                is_relative = False
            else:
                delta = max(abs_time - previous_time, 0.0)
                time_str = self._format_service.format_time(delta, ref)
                is_relative = True

            new_point = PwlPoint(time_str, point.value_str, is_relative=is_relative)
            formatted_points.append(new_point)
            previous_time = abs_time

        new_data.points = formatted_points
        new_data._values_discrete = []
        new_data._timestamps_discrete = []
        new_data._discrete_dirty = True
        return new_data


__all__ = [
    "DuplicateGroup",
    "TimeReversal",
    "WaveformAnalyzer",
    "WaveformRepairer",
]
