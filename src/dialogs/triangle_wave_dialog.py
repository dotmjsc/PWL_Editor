"""
Triangle waveform dialog for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from generators.triangle import (
    SYMMETRY_MAX,
    SYMMETRY_MIN,
    TriangleWaveConfig,
    TriangleWaveResult,
    TriangleWaveValidationError,
    generate_triangle_wave,
)
from pwl_parser import PwlData, PwlPoint, ltspice_si_parse
from services.formatting import FormatService


_LAST_SETTINGS: Optional[Dict[str, Any]] = None


class TriangleWaveGeneratorDialog:
    """Modal dialog that inserts a synthesized triangle waveform into the editor."""

    apply_mode_var: tk.StringVar
    start_time_entry: ttk.Entry

    def __init__(self, editor: Any, parent: Optional[tk.Tk] = None) -> None:
        self.editor = editor
        self.parent = parent or editor.root
        self.original_data: PwlData = editor.pwl_data
        self._original_snapshot = self._clone_data(self.original_data)
        self._format_service = FormatService()

        self.window = tk.Toplevel(self.parent)
        self.window.title("Generate Triangle Wave")
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        last_time = (
            self.original_data.timestamps[-1]
            if self.original_data.get_point_count() > 0
            else 0.0
        )
        default_start = self._format_service.format_time(last_time)

        self.low_level_var = tk.StringVar(value="0")
        self.high_level_var = tk.StringVar(value="5")
        self.period_var = tk.StringVar(value="1e-6")
        self.symmetry_var = tk.StringVar(value="0.5")
        self.cycles_var = tk.StringVar(value="5")
        self.start_time_var = tk.StringVar(value=default_start)
        self.prefer_relative_var = tk.BooleanVar(
            value=self.original_data.default_format == "relative"
        )
        self.apply_mode_var = tk.StringVar(value="append")

        self._apply_last_settings()

        self._preview_signature: Optional[tuple[TriangleWaveConfig, str]] = None
        self._preview_result: Optional[PwlData] = None
        self._current_warnings: List[str] = []
        self.applied_warnings: List[str] = []

        self._build_ui()
        self._center_window()

        self.result: Optional[PwlData] = None

    def _apply_last_settings(self) -> None:
        global _LAST_SETTINGS
        if not _LAST_SETTINGS:
            return

        config = _LAST_SETTINGS.get("config")
        apply_mode: str = _LAST_SETTINGS.get("apply_mode", "append")
        if apply_mode not in {"append", "replace"}:
            apply_mode = "append"
        if config is None:
            return

        self.low_level_var.set(self._format_service.format_value(config.low_level))
        self.high_level_var.set(self._format_service.format_value(config.high_level))
        self.period_var.set(self._format_service.format_time(config.period))
        self.symmetry_var.set(f"{config.symmetry:g}")
        self.cycles_var.set(str(config.cycles))
        self.start_time_var.set(self._format_service.format_time(config.start_time))
        self.prefer_relative_var.set(config.prefer_relative)
        self.apply_mode_var.set(apply_mode)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.window, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        form_frame = ttk.LabelFrame(main_frame, text="Triangle Wave Parameters")
        form_frame.grid(row=0, column=0, sticky="nsew")
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Low level").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Entry(form_frame, textvariable=self.low_level_var, width=14).grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))

        ttk.Label(form_frame, text="High level").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form_frame, textvariable=self.high_level_var, width=14).grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form_frame, text="Period (s)").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form_frame, textvariable=self.period_var, width=14).grid(row=2, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(
            form_frame,
            text=f"Symmetry ({SYMMETRY_MIN:g}-{SYMMETRY_MAX:g})",
        ).grid(row=3, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form_frame, textvariable=self.symmetry_var, width=14).grid(row=3, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form_frame, text="Cycles").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(form_frame, textvariable=self.cycles_var, width=14).grid(row=4, column=1, sticky="ew", padx=8, pady=4)

        ttk.Label(form_frame, text="Start time (s)").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        self.start_time_entry = ttk.Entry(form_frame, textvariable=self.start_time_var, width=14)
        self.start_time_entry.grid(row=5, column=1, sticky="ew", padx=8, pady=4)

        options_frame = ttk.Frame(form_frame)
        options_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        ttk.Checkbutton(options_frame, text="Prefer relative output", variable=self.prefer_relative_var).grid(row=0, column=0, sticky="w")

        apply_frame = ttk.LabelFrame(main_frame, text="Apply Mode")
        apply_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        for idx, (label, value) in enumerate((
            ("Append at end", "append"),
            ("Replace entire waveform", "replace"),
        )):
            ttk.Radiobutton(
                apply_frame,
                text=label,
                variable=self.apply_mode_var,
                value=value,
            ).grid(row=idx, column=0, sticky="w", padx=8, pady=2)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(button_frame, text="Preview", command=self._on_preview).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text="Apply", command=self._on_apply).grid(row=0, column=1, padx=4)
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).grid(row=0, column=2, padx=4)

        self.apply_mode_var.trace_add("write", lambda *_: self._update_start_time_state())
        self._update_start_time_state()

    def _center_window(self) -> None:
        self.window.update_idletasks()
        parent_geom = (
            self.parent.winfo_rootx(),
            self.parent.winfo_rooty(),
            self.parent.winfo_width(),
            self.parent.winfo_height(),
        )
        dialog_width = self.window.winfo_width()
        dialog_height = self.window.winfo_height()
        x = parent_geom[0] + (parent_geom[2] // 2) - (dialog_width // 2)
        y = parent_geom[1] + (parent_geom[3] // 2) - (dialog_height // 2)
        self.window.geometry(f"{dialog_width}x{dialog_height}+{max(x, 0)}+{max(y, 0)}")

    # ----------------------------------------------------------------- Flow

    def show(self) -> Optional[PwlData]:
        self.window.wait_window()
        return self.result

    # -------------------------------------------------------------- Handlers

    def _on_preview(self) -> None:
        settings = self._gather_settings()
        if settings is None:
            return

        self._remember_settings(settings["config"], settings["apply_mode"])
        signature = (settings["config"], settings["apply_mode"])
        preview_info = self._generate_preview(settings)
        if preview_info is None:
            return

        preview, warnings = preview_info

        self._apply_preview(preview, interim=True)
        self._preview_result = self.editor.pwl_data
        self._preview_signature = signature
        self._current_warnings = warnings
        summary = self._summarize_preview(preview, settings)
        if warnings:
            summary += " | Warnings: " + "; ".join(warnings)
        self.editor.status_var.set(
            f"Triangle wave preview applied (not saved). {summary}"
        )

    def _on_apply(self) -> None:
        settings = self._gather_settings()
        if settings is None:
            return

        self._remember_settings(settings["config"], settings["apply_mode"])
        signature = (settings["config"], settings["apply_mode"])
        reuse_preview = (
            self._preview_result is not None
            and self._preview_signature == signature
        )

        if reuse_preview:
            preview = self._preview_result
            warnings = list(self._current_warnings)
        else:
            preview_info = self._generate_preview(settings)
            if preview_info is None:
                return
            preview, warnings = preview_info
            self._apply_preview(preview, interim=False)

        if preview is None:
            return

        if preview is not self.editor.pwl_data:
            self._apply_preview(preview, interim=False)

        self.applied_warnings = warnings
        self.result = self.editor.pwl_data
        summary = self._summarize_preview(preview, settings)
        if warnings:
            summary += " | Warnings: " + "; ".join(warnings)
        self.editor.status_var.set(f"Triangle wave generated. {summary}")
        self._close_dialog()

    def _on_cancel(self) -> None:
        snapshot = self._gather_settings(show_errors=False)
        if snapshot is not None:
            self._remember_settings(snapshot["config"], snapshot["apply_mode"])
        self._restore_original()
        self.result = None
        self.editor.status_var.set(
            "Triangle wave generation cancelled; original data restored"
        )
        self._close_dialog()

    # ------------------------------------------------------------- Helpers

    def _gather_settings(
        self, *, show_errors: bool = True
    ) -> Optional[Dict[str, Any]]:
        try:
            low = self._parse_number(self.low_level_var.get())
            high = self._parse_number(self.high_level_var.get())
            period = self._parse_number(self.period_var.get())
            symmetry = float(self.symmetry_var.get())
            cycles = int(self.cycles_var.get())
            start_time = self._parse_number(self.start_time_var.get())
        except ValueError as exc:
            if show_errors:
                messagebox.showerror("Generate Triangle Wave", f"Invalid parameter: {exc}")
            return None

        if not SYMMETRY_MIN <= symmetry <= SYMMETRY_MAX:
            if show_errors:
                messagebox.showerror(
                    "Generate Triangle Wave",
                    f"Symmetry must be between {SYMMETRY_MIN:g} and {SYMMETRY_MAX:g}.",
                )
            return None

        config = TriangleWaveConfig(
            low_level=low,
            high_level=high,
            period=period,
            symmetry=symmetry,
            cycles=cycles,
            start_time=start_time,
            prefer_relative=self.prefer_relative_var.get(),
        )

        return {
            "config": config,
            "apply_mode": self.apply_mode_var.get(),
        }

    def _generate_preview(
        self, settings: Dict[str, Any]
    ) -> Optional[tuple[PwlData, List[str]]]:
        config: TriangleWaveConfig = settings["config"]

        try:
            result = generate_triangle_wave(config)
        except TriangleWaveValidationError as exc:
            messagebox.showerror("Generate Triangle Wave", str(exc))
            return None

        combined = self._compose_preview_data(
            result, config, settings["apply_mode"]
        )
        if combined is None:
            messagebox.showinfo(
                "Generate Triangle Wave", "Generation produced no points."
            )
            return None

        return combined, list(result.warnings)

    def _compose_preview_data(
        self,
        generated: TriangleWaveResult,
        config: TriangleWaveConfig,
        apply_mode: str,
    ) -> Optional[PwlData]:
        generated_data = self._clone_data(generated.data)
        if generated_data.get_point_count() == 0:
            return None

        if apply_mode == "replace":
            generated_data.timestep = self._original_snapshot.timestep
            return generated_data

        base_clone = self._clone_data(self._original_snapshot)
        appended_points = self._build_appended_points(base_clone, generated_data)
        base_clone.points.extend(appended_points)

        base_clone._values_discrete = []
        base_clone._timestamps_discrete = []
        base_clone._discrete_dirty = True
        return base_clone

    def _build_appended_points(
        self, base_data: PwlData, addition: PwlData
    ) -> List[PwlPoint]:
        if addition.get_point_count() == 0:
            return []

        if base_data.get_point_count() == 0:
            return [
                PwlPoint(point.time_str, point.value_str, point.is_relative)
                for point in addition.points
            ]

        base_times = base_data.timestamps
        addition_times = addition.timestamps

        base_last_time = base_times[-1]
        first_addition_time = addition_times[0]
        previous_abs = base_last_time
        relative_mode = addition.default_format == "relative"

        appended: List[PwlPoint] = []
        reference_point = base_data.points[-1]
        addition_values = addition.values

        for idx, point in enumerate(addition.points):
            abs_time = addition_times[idx]
            adjusted_abs = base_last_time + max(abs_time - first_addition_time, 0.0)
            value_numeric = addition_values[idx]

            if relative_mode:
                delta = max(adjusted_abs - previous_abs, 0.0)
                if delta != 0.0:
                    delta = float(f"{delta:.12g}")
                time_str = self._format_service.format_time(
                    delta, reference_point
                )
                value_str = self._format_service.format_value(
                    value_numeric, reference_point
                )
                new_point = PwlPoint(time_str, value_str, is_relative=True)
            else:
                time_str = self._format_service.format_time(adjusted_abs)
                value_str = self._format_service.format_value(
                    value_numeric, reference_point
                )
                new_point = PwlPoint(time_str, value_str, is_relative=False)

            appended.append(new_point)
            previous_abs = adjusted_abs
            reference_point = new_point

        return appended

    def _remember_settings(self, config: TriangleWaveConfig, apply_mode: str) -> None:
        global _LAST_SETTINGS
        _LAST_SETTINGS = {"config": config, "apply_mode": apply_mode}

    def _apply_preview(self, preview: PwlData, *, interim: bool) -> None:
        editor = self.editor
        editor._undo_in_progress = True
        try:
            editor.pwl_data = preview
            editor.update_table()
            editor.table_to_text_with_format()
            editor.update_plot()
        finally:
            editor._undo_in_progress = False

    def _restore_original(self) -> None:
        self._apply_preview(self._clone_data(self._original_snapshot), interim=True)

    def _close_dialog(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()

    def _summarize_preview(self, data: PwlData, settings: Dict[str, Any]) -> str:
        total_points = data.get_point_count()
        times = data.timestamps
        if not times:
            return "Preview contains no points"
        start = self._format_service.format_time(
            times[0], SimpleNamespace(time_str="0")
        )
        end = self._format_service.format_time(
            times[-1], SimpleNamespace(time_str="0")
        )
        mode_labels = {
            "append": "Append at end",
            "replace": "Replace entire waveform",
        }
        mode_text = mode_labels.get(settings["apply_mode"], settings["apply_mode"])
        return (
            f"Preview: {total_points} points spanning {start} → {end}\n"
            f"Apply mode: {mode_text}"
        )

    @staticmethod
    def _clone_data(data: PwlData) -> PwlData:
        clone = PwlData()
        clone.timestep = data.timestep
        clone.default_format = data.default_format
        clone.points = [
            PwlPoint(point.time_str, point.value_str, point.is_relative)
            for point in data.points
        ]
        clone._values_discrete = []
        clone._timestamps_discrete = []
        clone._discrete_dirty = True
        return clone

    @staticmethod
    def _parse_number(value: str) -> float:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        try:
            return float(stripped)
        except ValueError:
            parsed = ltspice_si_parse(stripped)
            if parsed is None:
                raise ValueError(f"could not parse '{value}'")
            return float(parsed)

    def _update_start_time_state(self) -> None:
        disable = self.apply_mode_var.get() == "append"
        state = "disabled" if disable else "normal"
        self.start_time_entry.configure(state=state)


__all__ = ["TriangleWaveGeneratorDialog"]
