"""
Text controller for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

from typing import Any, Callable, Dict

import tkinter as tk

from pwl_parser import PwlData


class TextController:
    _EXPORT_FORMAT_LABEL_TO_CODE: Dict[str, str] = {
        "Preserve Mixed": "preserve_mixed",
        "Force Relative": "force_relative",
        "Force Absolute": "force_absolute",
    }
    _EXPORT_FORMAT_CODE_TO_LABEL: Dict[str, str] = {
        v: k for k, v in _EXPORT_FORMAT_LABEL_TO_CODE.items()
    }
    _DEFAULT_EXPORT_FORMAT_LABEL = "Preserve Mixed"

    def __init__(self, editor: Any, pwl_data_factory: Callable[[], Any] | None = None):
        self.editor = editor
        self._pwl_data_factory: Callable[[], Any] = pwl_data_factory or PwlData
        # Lazily normalized once widgets are available
        self._export_format_initialized = False

    @property
    def pwl_data(self) -> PwlData:
        return self.editor.pwl_data

    def table_to_text(self):
        try:
            export_var = self._normalize_export_format_var()
            if export_var is None:
                text_content = self.pwl_data.to_text_precise(use_relative_time=True, precision=9, preserve_original=True)
                self.editor.text_editor.delete(1.0, tk.END)
                self.editor.text_editor.insert(1.0, text_content)
            else:
                # Defer to format-aware path when dropdown is wired
                self.table_to_text_with_format()
        except Exception as e:
            self.editor.status_var.set(f"Error updating text: {e}")

    def text_to_table(self):
        """Handle text-to-table conversion with proper undo integration"""
        try:
            text_content = self.editor.text_editor.get(1.0, tk.END).strip()
            if text_content:
                new_pwl_data = self._pwl_data_factory()
                if new_pwl_data.load_from_text(text_content):
                    self.editor._operation_description = "Text to table conversion"
                    self.editor.pwl_data = new_pwl_data
                    self.editor.update_table()
                    self.editor.update_plot()  # This will create the undo point
                    self.editor.mark_unsaved()
                else:
                    self.editor.status_var.set("Invalid PWL text format")
            else:
                # Handle empty text - convert to empty data
                self.editor._operation_description = "Clear all data"
                self.editor.pwl_data = self._pwl_data_factory()
                self.editor.update_table()
                self.editor.update_plot()  # This will create the undo point
                self.editor.mark_unsaved()
        except Exception as e:
            self.editor.status_var.set(f"Error parsing text: {e}")

    def on_export_format_changed(self, event=None):
        """Handle export format dropdown change - store setting but don't apply immediately"""
        try:
            label = self._get_selected_export_format_label()
            self.editor.status_var.set(f"Export format set to: {label} (applies on save)")
        except Exception:
            # Non-fatal UX
            pass

    def table_to_text_with_format(self):
        """Update text editor using the selected export format"""
        try:
            selected_format = self._get_selected_export_format_code()
            # Preserve original formatting where applicable
            text_content = self.pwl_data.to_text_with_format(
                export_format=selected_format, precision=9, preserve_original=True
            )

            self.editor.text_editor.delete(1.0, tk.END)
            self.editor.text_editor.insert(1.0, text_content)
        except Exception as e:
            self.editor.status_var.set(f"Error updating text format: {e}")

    def get_formatted_content_for_save(self, *, apply_export_format: bool = True) -> str:
        """Return content ready for persistence, optionally applying the export preset."""
        try:
            # First ensure data is synchronized from text editor
            self.text_to_table()

            if not apply_export_format:
                return self.editor.text_editor.get(1.0, tk.END).strip()

            selected_format = self._get_selected_export_format_code()

            # Apply the selected export format
            if selected_format == "preserve_mixed":
                # Use current text editor content as-is
                return self.editor.text_editor.get(1.0, tk.END).strip()
            else:
                # Apply the selected format transformation
                formatted_content = self.pwl_data.to_text_with_format(
                    export_format=selected_format,
                    precision=9,
                    preserve_original=True,
                )
                return formatted_content.strip()

        except Exception as e:
            self.editor.status_var.set(f"Error formatting content for save: {e}")
            # Fallback to current text editor content
            return self.editor.text_editor.get(1.0, tk.END).strip()

    def initialize_export_format_default(self):
        """Ensure the Tkinter export_format_var reflects a known display label."""
        self._normalize_export_format_var(force_refresh=True)

    def _normalize_export_format_var(self, force_refresh: bool = False):
        """Normalize the export_format_var to a known display label and return it when present."""
        try:
            export_var = getattr(self.editor, "export_format_var", None)
        except Exception:
            return None

        if export_var is None:
            return None

        if not force_refresh and self._export_format_initialized:
            return export_var

        try:
            current_value = export_var.get()
        except Exception:
            current_value = None

        if current_value in self._EXPORT_FORMAT_LABEL_TO_CODE:
            normalized_label = current_value
        elif current_value in self._EXPORT_FORMAT_CODE_TO_LABEL:
            normalized_label = self._EXPORT_FORMAT_CODE_TO_LABEL[current_value]
        else:
            normalized_label = self._DEFAULT_EXPORT_FORMAT_LABEL

        try:
            export_var.set(normalized_label)
        except Exception:
            # If setting fails, leave as-is but continue with normalized label
            pass

        self._export_format_initialized = True
        return export_var

    def _get_selected_export_format_label(self) -> str:
        export_var = self._normalize_export_format_var()
        if export_var is None:
            return self._DEFAULT_EXPORT_FORMAT_LABEL
        try:
            label = export_var.get()
        except Exception:
            return self._DEFAULT_EXPORT_FORMAT_LABEL
        if label in self._EXPORT_FORMAT_LABEL_TO_CODE:
            return label
        return self._DEFAULT_EXPORT_FORMAT_LABEL

    def _get_selected_export_format_code(self) -> str:
        label = self._get_selected_export_format_label()
        return self._EXPORT_FORMAT_LABEL_TO_CODE.get(label, "preserve_mixed")
