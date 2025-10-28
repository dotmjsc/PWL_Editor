"""
Table selection controller for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

from typing import Any, List


class TableController:
    def __init__(self, editor: Any):
        self.editor = editor

    @property
    def table(self):
        return self.editor.table

    def on_table_select(self, event=None):
        try:
            selected_items = self.table.selection()
            current_selection = list(selected_items) if selected_items else []

            if current_selection:
                should_update_previous = True
                if (self.editor.previous_selection and len(self.editor.previous_selection) > 1 and 
                    len(current_selection) == 1 and current_selection[0] in self.editor.previous_selection):
                    should_update_previous = False
                if should_update_previous:
                    self.editor.previous_selection = current_selection

            selected_indices: List[int] = []
            if selected_items:
                children = self.table.get_children()
                for item in selected_items:
                    if item in children:
                        selected_indices.append(children.index(item))

            self.editor._update_plot_internal(selected_indices if selected_indices else None)
        except Exception:
            # Fail silently - highlighting is a nice-to-have feature
            pass
