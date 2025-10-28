"""
Waveform repair dialog for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional, TYPE_CHECKING

from pwl_parser import PwlData, PwlPoint
from services.waveform_repair import WaveformAnalyzer, WaveformRepairer

if TYPE_CHECKING:
    from pwl_gui import PWLEditor


class WaveformRepairDialog:
    """Modal dialog that analyzes waveform issues and applies repairs."""

    def __init__(self, editor: Any, parent: Optional[tk.Tk] = None) -> None:
        self.editor: "PWLEditor" = editor  # type: ignore[assignment]
        self.parent = parent or editor.root
        self.original_data: PwlData = editor.pwl_data
        self._original_snapshot = self._clone_data(self.original_data)
        self._time_epsilon = 1e-15

        self.window = tk.Toplevel(self.parent)
        self.window.title("Repair Waveform")
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.max_slew_var = tk.StringVar(value="1e8")
        self.time_tolerance_var = tk.StringVar(value="1e-12")
        self.duplicate_strategy_var = tk.StringVar(value="center")
        self.reversal_strategy_var = tk.StringVar(value="sort")
        self.issue_summary_var = tk.StringVar(value="Analyzing...")

        self._preview_settings: Optional[Dict[str, Any]] = None
        self._preview_result: Optional[PwlData] = None

        self._build_ui()
        self._run_initial_analysis()

        # Center dialog relative to parent
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

        self.result: Optional[PwlData] = None

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.window, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        # Issue summary frame
        issues_frame = ttk.LabelFrame(main_frame, text="Detected Issues")
        issues_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        issues_frame.columnconfigure(0, weight=1)

        issue_label = ttk.Label(issues_frame, textvariable=self.issue_summary_var, justify=tk.LEFT)
        issue_label.grid(row=0, column=0, sticky="w", padx=8, pady=6)

        # Repair settings
        settings_frame = ttk.LabelFrame(main_frame, text="Repair Settings")
        settings_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="Max Slew Rate (V/s)").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Entry(settings_frame, textvariable=self.max_slew_var, width=14).grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 4))

        ttk.Label(settings_frame, text="Minimum Time Gap (s)").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(settings_frame, textvariable=self.time_tolerance_var, width=14).grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        dup_frame = ttk.LabelFrame(settings_frame, text="Duplicate Timestamps")
        dup_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        duplicate_options = (
            ("Leave as-is", "none"),
            ("Balance around original time", "center"),
            ("Shift forward from original time", "shift_right"),
            ("Shift backward to original time", "shift_left"),
        )
        for idx, (label, value) in enumerate(duplicate_options):
            ttk.Radiobutton(dup_frame, text=label, variable=self.duplicate_strategy_var, value=value).grid(row=idx, column=0, sticky="w", padx=8, pady=2)

        rev_frame = ttk.LabelFrame(settings_frame, text="Time Reversals")
        rev_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 12))
        reversal_options = (
            ("Leave as-is", "none"),
            ("Sort chronologically", "sort"),
            ("Remove offending points", "remove"),
        )
        for idx, (label, value) in enumerate(reversal_options):
            ttk.Radiobutton(rev_frame, text=label, variable=self.reversal_strategy_var, value=value).grid(row=idx, column=0, sticky="w", padx=8, pady=2)

        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

        ttk.Button(button_frame, text="Analyze", command=self._on_analyze).grid(row=0, column=0, padx=4)
        ttk.Button(button_frame, text="Preview", command=self._on_preview).grid(row=0, column=1, padx=4)
        ttk.Button(button_frame, text="Apply Repair", command=self._on_apply).grid(row=0, column=2, padx=4)
        ttk.Button(button_frame, text="Cancel", command=self._on_cancel).grid(row=0, column=3, padx=4)

    # ----------------------------------------------------------------- Flow

    def show(self) -> Optional[PwlData]:
        self.window.wait_window()
        return self.result

    # -------------------------------------------------------------- Handlers

    def _run_initial_analysis(self) -> None:
        self._update_issue_summary(self._original_snapshot)

    def _on_analyze(self) -> None:
        self._update_issue_summary(self.editor.pwl_data)
        self._preview_settings = None
        self._preview_result = None

    def _on_preview(self) -> None:
        settings = self._gather_settings()
        if settings is None:
            return

        preview = self._generate_preview(settings)
        if preview is None:
            messagebox.showinfo("Repair Waveform", "No repairs were necessary.")
            return

        self._apply_preview(preview, interim=True)
        self._preview_settings = settings
        self._preview_result = self.editor.pwl_data

    def _on_apply(self) -> None:
        settings = self._gather_settings()
        if settings is None:
            return

        preview = self._preview_result if self._preview_settings == settings and self._preview_result is not None else self._generate_preview(settings)
        if preview is None:
            messagebox.showinfo("Repair Waveform", "No repairs were necessary.")
            self.result = None
            self._close_dialog()
            return

        # Ensure final state is applied to editor
        if preview is not self.editor.pwl_data:
            self._apply_preview(preview, interim=False)

        self.result = self.editor.pwl_data
        self._close_dialog()

    def _on_cancel(self) -> None:
        self._restore_original()
        self.result = None
        self._close_dialog()

    # ------------------------------------------------------------- Helpers

    def _gather_settings(self) -> Optional[Dict[str, Any]]:
        try:
            max_slew = float(self.max_slew_var.get())
            time_tol = float(self.time_tolerance_var.get())
        except ValueError:
            messagebox.showerror("Repair Waveform", "Please enter valid numeric values for slew rate and time tolerance.")
            return None

        if max_slew <= 0 or time_tol <= 0:
            messagebox.showerror("Repair Waveform", "Slew rate and time tolerance must be positive numbers.")
            return None

        return {
            "max_slew_rate": max_slew,
            "time_tolerance": time_tol,
            "duplicate_strategy": self.duplicate_strategy_var.get(),
            "reversal_strategy": self.reversal_strategy_var.get(),
        }

    def _generate_preview(self, settings: Dict[str, Any]) -> Optional[PwlData]:
        base = self._clone_data(self._original_snapshot)
        analyzer = WaveformAnalyzer(base, time_epsilon=self._time_epsilon)
        dup_strategy = str(settings["duplicate_strategy"]).lower()
        rev_strategy = str(settings["reversal_strategy"]).lower()
        duplicates = analyzer.find_duplicate_timestamps() if dup_strategy != "none" else []
        reversals = analyzer.find_time_reversals() if rev_strategy != "none" else []

        if not duplicates and not reversals:
            return None

        data = base
        if duplicates:
            repairer = WaveformRepairer(data, time_epsilon=self._time_epsilon)
            data = repairer.repair_duplicates(
                max_slew_rate=settings["max_slew_rate"],
                time_tolerance=settings["time_tolerance"],
                strategy=settings["duplicate_strategy"],
            )

        if reversals:
            repairer = WaveformRepairer(data, time_epsilon=self._time_epsilon)
            data = repairer.repair_time_reversals(strategy=settings["reversal_strategy"])

        if self._data_equals(data, self._original_snapshot):
            return None

        return data

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

        self._update_issue_summary(preview)

        if interim:
            editor.status_var.set("Waveform repair preview applied (not saved)")
        else:
            editor.status_var.set("Waveform repair applied")

    def _restore_original(self) -> None:
        self._apply_preview(self._clone_data(self._original_snapshot), interim=True)
        # After restoration, refresh undo-less updates to original state
        self.editor.status_var.set("Waveform repair cancelled; original data restored")

    def _close_dialog(self) -> None:
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        self.window.destroy()

    def _update_issue_summary(self, data: PwlData) -> None:
        summary = self._summarize_issues(data)
        self.issue_summary_var.set(summary)

    def _summarize_issues(self, data: PwlData) -> str:
        analyzer = WaveformAnalyzer(data, time_epsilon=self._time_epsilon)
        duplicates = analyzer.find_duplicate_timestamps()
        reversals = analyzer.find_time_reversals()

        lines = []
        if not duplicates and not reversals:
            return "No issues detected."

        if duplicates:
            total_points = sum(len(group.indices) for group in duplicates)
            lines.append(f"Duplicate timestamp groups: {len(duplicates)} ({total_points} points)")
        else:
            lines.append("Duplicate timestamp groups: 0")

        if reversals:
            lines.append(f"Time reversals: {len(reversals)}")
        else:
            lines.append("Time reversals: 0")

        return "\n".join(lines)

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
    def _data_equals(first: PwlData, second: PwlData) -> bool:
        if first.get_point_count() != second.get_point_count():
            return False
        for a, b in zip(first.points, second.points):
            if (a.time_str, a.value_str, a.is_relative) != (b.time_str, b.value_str, b.is_relative):
                return False
        return True


__all__ = ["WaveformRepairDialog"]
