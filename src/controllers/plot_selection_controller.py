"""
Plot selection controller for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple
from dataclasses import dataclass, field


@dataclass
class SelectionState:
    """Encapsulates selection-related state for plot interactions.
    Mirrors editor attributes for backward-compatibility."""
    is_dragging: bool = False
    drag_start_pos: Optional[Tuple[float, float]] = None
    selection_rect: Any = None
    plot_event_connections: Dict[str, Optional[int]] = field(default_factory=dict)


class PlotSelectionController:
    def __init__(self, editor: Any):
        # Weak coupling: we use the editor for state, ax/canvas, and helpers
        self.editor = editor
        # Initialize internal state from editor to preserve current behavior
        self.state = SelectionState(
            is_dragging=getattr(editor, 'is_dragging', False),
            drag_start_pos=getattr(editor, 'drag_start_pos', None),
            selection_rect=getattr(editor, 'selection_rect', None),
            plot_event_connections=dict(getattr(editor, 'plot_event_connections', {}) or {}),
        )
        # Ensure editor mirrors our authoritative state
        self._mirror_all_to_editor()

    # --- State accessors that mirror editor attributes for compatibility ---
    def _get_is_dragging(self) -> bool:
        return self.state.is_dragging

    def _set_is_dragging(self, value: bool) -> None:
        self.state.is_dragging = bool(value)
        self.editor.is_dragging = bool(value)

    def _get_drag_start_pos(self) -> Optional[Tuple[float, float]]:
        return self.state.drag_start_pos

    def _set_drag_start_pos(self, value: Optional[Tuple[float, float]]) -> None:
        self.state.drag_start_pos = value
        self.editor.drag_start_pos = value

    def _get_selection_rect(self):
        return self.state.selection_rect

    def _set_selection_rect(self, rect) -> None:
        self.state.selection_rect = rect
        self.editor.selection_rect = rect

    def _get_connections(self) -> Dict[str, Optional[int]]:
        return self.state.plot_event_connections

    def _set_connections(self, new_map: Dict[str, Optional[int]]) -> None:
        # Replace internal map and mirror a shallow copy to editor
        self.state.plot_event_connections = new_map
        self.editor.plot_event_connections = dict(new_map)

    def _mirror_all_to_editor(self) -> None:
        self.editor.is_dragging = self.state.is_dragging
        self.editor.drag_start_pos = self.state.drag_start_pos
        self.editor.selection_rect = self.state.selection_rect
        self.editor.plot_event_connections = dict(self.state.plot_event_connections)

    # Small helper proxies keep original behavior and guard clauses centralized
    @property
    def ax(self):
        return self.editor.ax

    @property
    def canvas(self):
        return self.editor.canvas

    @property
    def notebook(self):
        return self.editor.notebook

    @property
    def table(self):
        return self.editor.table

    # State that previously lived on the editor remains on editor; we read/write via editor
    @property
    def NEAREST_PX_TOL(self) -> int:
        return self.editor.NEAREST_PX_TOL

    @property
    def DRAG_THRESHOLD_PX(self) -> int:
        return self.editor.DRAG_THRESHOLD_PX

    def on_plot_press(self, event):
        try:
            selected_tab = self.notebook.select()
            tab_text = self.notebook.tab(selected_tab, 'text')
            if tab_text != 'Table':
                return

            if (self.editor.edit_entry is not None or self.editor.edit_combo is not None or 
                self.editor.edit_item is not None):
                return

            if event.button != 1:
                return

            # Clear any previous selection rectangle before starting a new gesture
            self._clear_selection_rect()

            sx, sy = self.editor._clamp_pixel_to_axes(event.x, event.y)
            self._set_drag_start_pos((sx, sy))
            self._set_is_dragging(False)
        except Exception:
            pass

    def on_plot_motion(self, event):
        try:
            selected_tab = self.notebook.select()
            tab_text = self.notebook.tab(selected_tab, 'text')
            if tab_text != 'Table':
                return

            if (self.editor.edit_entry is not None or self.editor.edit_combo is not None or 
                self.editor.edit_item is not None):
                return

            if not self._get_drag_start_pos():
                return

            start = self._get_drag_start_pos()
            if not start:
                return
            dx = event.x - start[0]
            dy = event.y - start[1]
            drag_distance = (dx*dx + dy*dy)**0.5

            if drag_distance >= self.DRAG_THRESHOLD_PX:
                self._set_is_dragging(True)
                cx, cy = self.editor._clamp_pixel_to_axes(event.x, event.y)
                # Update the in-progress selection rectangle
                self.update_selection_rectangle(self._get_drag_start_pos(), (cx, cy))
        except Exception:
            pass

    def on_plot_release(self, event):
        try:
            selected_tab = self.notebook.select()
            tab_text = self.notebook.tab(selected_tab, 'text')
            if tab_text != 'Table':
                return

            if (self.editor.edit_entry is not None or self.editor.edit_combo is not None or 
                self.editor.edit_item is not None):
                return

            if event.button != 1:
                return

            if not self._get_drag_start_pos():
                return

            if self._get_is_dragging():
                start = self._get_drag_start_pos()
                if not start:
                    return
                sx, sy = self.editor._clamp_pixel_to_axes(start[0], start[1])
                ex, ey = self.editor._clamp_pixel_to_axes(event.x, event.y)
                start_data = self.editor.pixel_to_data(sx, sy)
                end_data = self.editor.pixel_to_data(ex, ey)

                if (start_data[0] is not None and end_data[0] is not None and
                    start_data[1] is not None and end_data[1] is not None):
                    selected_indices = self.editor.find_points_in_box(start_data, end_data)

                    if selected_indices:
                        self.table.selection_remove(self.table.selection())
                        children = self.table.get_children()
                        for index in selected_indices:
                            if 0 <= index < len(children):
                                self.table.selection_add(children[index])
                        self.editor._update_plot_internal(selected_indices)
                    else:
                        self.table.selection_remove(self.table.selection())
                        self.editor._update_plot_internal(None)
            else:
                cx, cy = self.editor._clamp_pixel_to_axes(event.x, event.y)
                if cx is None or cy is None:
                    return
                nearest_index = self.editor.find_nearest_point(cx, cy)

                if nearest_index is not None:
                    self.table.selection_remove(self.table.selection())
                    children = self.table.get_children()
                    if 0 <= nearest_index < len(children):
                        self.table.selection_add(children[nearest_index])
                    self.editor._update_plot_internal([nearest_index])
                else:
                    self.table.selection_remove(self.table.selection())
                    self.editor._update_plot_internal(None)

            # Final cleanup of any selection rectangle
            self._clear_selection_rect()

            self._set_drag_start_pos(None)
            self._set_is_dragging(False)
        except Exception:
            self._set_drag_start_pos(None)
            self._set_is_dragging(False)
            # Best-effort cleanup
            self._clear_selection_rect()

    def connect_plot_events(self):
        try:
            self.disconnect_plot_events()
            connections = self._get_connections()
            connections['button_press'] = self.canvas.mpl_connect(
                'button_press_event', self.on_plot_press)
            connections['motion_notify'] = self.canvas.mpl_connect(
                'motion_notify_event', self.on_plot_motion)
            connections['button_release'] = self.canvas.mpl_connect(
                'button_release_event', self.on_plot_release)
            # Mirror to editor
            self._set_connections(connections)
        except Exception:
            pass

    def disconnect_plot_events(self):
        try:
            for event_type, connection_id in self._get_connections().items():
                if connection_id is not None:
                    self.canvas.mpl_disconnect(connection_id)
            self._set_connections({})

            # Remove any lingering selection rectangle on disconnect
            self._clear_selection_rect()

            self._set_drag_start_pos(None)
            self._set_is_dragging(False)
        except Exception:
            pass

    # --- Helper logic moved from editor ---
    def find_nearest_point(self, pixel_x: float, pixel_y: float):
        try:
            if self.editor.pwl_data.get_point_count() == 0:
                return None

            times = self.editor.pwl_data.timestamps
            values = self.editor.pwl_data.values

            nearest_index = None
            min_distance = float('inf')

            for i, (time, value) in enumerate(zip(times, values)):
                px, py = self.editor.data_to_pixel(time, value)
                if px is None or py is None:
                    continue
                distance = ((pixel_x - px)**2 + (pixel_y - py)**2)**0.5
                if distance < min_distance and distance <= self.NEAREST_PX_TOL:
                    min_distance = distance
                    nearest_index = i

            return nearest_index
        except Exception:
            return None

    def find_points_in_box(self, start_data, end_data):
        try:
            if self.editor.pwl_data.get_point_count() == 0:
                return []

            min_time = min(start_data[0], end_data[0])
            max_time = max(start_data[0], end_data[0])
            min_value = min(start_data[1], end_data[1])
            max_value = max(start_data[1], end_data[1])

            times = self.editor.pwl_data.timestamps
            values = self.editor.pwl_data.values

            selected_indices = []
            for i, (time, value) in enumerate(zip(times, values)):
                if (min_time <= time <= max_time and min_value <= value <= max_value):
                    selected_indices.append(i)

            return selected_indices
        except Exception:
            return []

    def update_selection_rectangle(self, start_pixel, end_pixel):
        try:
            rect = self._get_selection_rect()
            if rect:
                try:
                    rect.remove()
                except Exception:
                    pass
                finally:
                    self._set_selection_rect(None)

            start_data = self.editor.pixel_to_data(start_pixel[0], start_pixel[1])
            end_data = self.editor.pixel_to_data(end_pixel[0], end_pixel[1])

            if (start_data[0] is None or end_data[0] is None or
                start_data[1] is None or end_data[1] is None):
                return

            min_x = min(start_data[0], end_data[0])
            max_x = max(start_data[0], end_data[0])
            min_y = min(start_data[1], end_data[1])
            max_y = max(start_data[1], end_data[1])

            from matplotlib.patches import Rectangle
            rect_width = max_x - min_x
            rect_height = max_y - min_y

            new_rect = Rectangle(
                (min_x, min_y), rect_width, rect_height,
                linewidth=2, edgecolor='red', facecolor='red', alpha=0.2
            )
            self._set_selection_rect(new_rect)
            self.ax.add_patch(self._get_selection_rect())
            self.canvas.draw()
        except Exception:
            pass

    # --- Internal helpers ---
    def _clear_selection_rect(self):
        """Safely remove and clear the current selection rectangle, if any."""
        try:
            rect = self._get_selection_rect()
            if rect:
                try:
                    rect.remove()
                except Exception:
                    pass
                finally:
                    self._set_selection_rect(None)
                # Drawing is safe even if nothing changed; keep UI in sync
                try:
                    self.canvas.draw()
                except Exception:
                    pass
        except Exception:
            # Best-effort cleanup; ignore all errors
            pass

    # Public wrapper to allow editor to clear rectangle without touching internals
    def clear_selection_rect(self):
        self._clear_selection_rect()
