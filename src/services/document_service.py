"""
Document management workflows for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

from typing import Any, Callable
import os
from tkinter import messagebox

from pwl_parser import PwlData


class DocumentService:
    def __init__(self, editor: Any, pwl_data_factory: Callable[[], Any] | None = None):
        self.editor = editor
        self._pwl_data_factory: Callable[[], Any] = pwl_data_factory or PwlData

    # --- Helper callbacks ---
    @property
    def file_service(self):
        return self.editor.file_service

    @property
    def text_controller(self):
        return self.editor.text_controller

    def _set_status(self, msg: str):
        try:
            self.editor.status_var.set(msg)
        except Exception:
            pass

    def _update_title(self):
        try:
            self.editor.update_title()
        except Exception:
            pass

    def _update_views_no_undo(self):
        # Update views WITHOUT creating undo points
        self.editor._undo_in_progress = True
        try:
            self.editor.update_table()
            self.editor._update_plot_internal()
            self.editor.table_to_text()
        finally:
            self.editor._undo_in_progress = False

    def _establish_baseline(self, description: str):
        if hasattr(self.editor, 'undo_manager'):
            self.editor.undo_manager.clear_history()
            self.editor.undo_manager.save_state(self.editor.pwl_data, description)

    # --- Public operations ---
    def new_file(self):
        if self.editor.check_unsaved_changes():
            self.editor.pwl_data.clear()
            self.editor.current_file = None

            self._update_views_no_undo()
            self.editor.unsaved_changes = False
            self._update_title()
            self._set_status("New file created")

            self._establish_baseline("New file")

    def open_file(self):
        if not self.editor.check_unsaved_changes():
            return

        file_path = self.file_service.ask_open(initial_dir=self.editor.get_initial_dir())
        if not file_path:
            return

        try:
            # Mirror internal last_directory for backward compatibility
            self.editor.last_directory = os.path.dirname(file_path)

            new_pwl_data = self._pwl_data_factory()
            if new_pwl_data.load_from_file(file_path, 0.001):  # Default 1ms timestep
                self.editor.pwl_data = new_pwl_data
                self.editor.current_file = file_path

                self._update_views_no_undo()
                self.editor.unsaved_changes = False
                self._update_title()
                self._set_status(f"Loaded: {os.path.basename(file_path)}")

                # Clear undo history AFTER loading file and establish new baseline
                self._establish_baseline(f"Opened: {os.path.basename(file_path)}")
            else:
                messagebox.showerror("Error", "Failed to load PWL file")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")

    def save_file(self):
        if self.editor.current_file:
            # Ask for confirmation when overwriting existing file
            if os.path.exists(self.editor.current_file):
                result = messagebox.askyesno(
                    "Confirm Save",
                    f"Overwrite existing file?\n\n{os.path.basename(self.editor.current_file)}",
                    icon='question'
                )
                if not result:
                    return

            try:
                text_content = self.editor._get_formatted_content_for_save(apply_export_format=False)
                if text_content:
                    with open(self.editor.current_file, 'w') as f:
                        f.write(text_content)

                    self.editor.unsaved_changes = False
                    self._update_title()
                    self._set_status(f"Saved: {os.path.basename(self.editor.current_file)}")
                else:
                    messagebox.showwarning("Save Warning", "No content to save")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file: {e}")
        else:
            self.save_file_as()

    def save_file_as(self):
        file_path = self.file_service.ask_save_as(initial_dir=self.editor.get_initial_dir(), defaultextension=".pwl")
        if not file_path:
            return
        try:
            # Mirror internal last_directory for backward compatibility
            self.editor.last_directory = os.path.dirname(file_path)

            text_content = self.editor._get_formatted_content_for_save(apply_export_format=False)
            if text_content:
                with open(file_path, 'w') as f:
                    f.write(text_content)

                self.editor.current_file = file_path
                self.editor.unsaved_changes = False
                self._update_title()
                self._set_status(f"Saved: {os.path.basename(file_path)}")
            else:
                messagebox.showwarning("Save Warning", "No content to save")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def export_file(self):
        file_path = self.file_service.ask_save_as(
            initial_dir=self.editor.get_initial_dir(),
            defaultextension=".pwl",
        )
        if not file_path:
            return

        previous_unsaved = getattr(self.editor, 'unsaved_changes', False)
        try:
            # Mirror internal last_directory for backward compatibility
            self.editor.last_directory = os.path.dirname(file_path)

            text_content = self.editor._get_formatted_content_for_save(apply_export_format=True)
            if not text_content:
                messagebox.showwarning("Export Warning", "No content to export")
                return

            with open(file_path, 'w') as f:
                f.write(text_content)

            self._set_status(f"Exported: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export file: {e}")
        finally:
            self.editor.unsaved_changes = previous_unsaved
            self._update_title()
