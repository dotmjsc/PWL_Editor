"""
PWL Editor Application - Main Application Logic
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
from types import SimpleNamespace
from typing import Sequence
from pwl_parser import PwlData, PwlPoint
from pwl_gui_geometry import PWLEditorGeometry
from services.insertion_service import SmartInsertion
from services.undo_history import UndoRedoManager
from version import get_version, get_version_info
from utils.plot_coordinates import data_to_pixel as util_data_to_pixel, pixel_to_data as util_pixel_to_data, clamp_pixel_to_axes as util_clamp
from services.file_service import FileService
from services.formatting import FormatService
from services.document_service import DocumentService
from controllers.plot_selection_controller import PlotSelectionController
from controllers.table_controller import TableController
from controllers.text_controller import TextController

class PWLEditor:
    def __init__(self, root):
        self.root = root
        
        self.pwl_data = PwlData()
        self.current_file = None
        self.unsaved_changes = False
        self.last_directory = None  # Remember last used directory
        
        # Undo/Redo functionality
        self.undo_manager = UndoRedoManager(max_history=50)
        self._operation_description = ""  # Track current operation for undo descriptions
        self._undo_in_progress = False    # Prevent recursive undo point creation
        
        self.edit_entry = None
        self.edit_combo = None
        self.edit_item = None
        self.edit_column = None
        
        # Multi-selection preservation for editing
        # Store the selection before current one (list of Treeview item IDs) or None
        self.previous_selection = None
        
        # Plot-to-table selection constants and state
        self.NEAREST_PX_TOL = 10    # Pixel tolerance for nearest-point selection
        self.DRAG_THRESHOLD_PX = 5  # Minimum pixels to trigger drag selection
        self.is_dragging = False    # Track if currently dragging for selection
        self.drag_start_pos = None  # Starting position for drag selection (pixel coords)
        self.selection_rect = None  # Current selection rectangle artist
        self.plot_event_connections = {}  # Store matplotlib event connection IDs
        
        # Initialize smart insertion handler
        self.smart_insertion = SmartInsertion()
        # Initialize file service
        self.file_service = FileService()
        # Initialize plot selection controller (delegates event logic)
        self.plot_controller = PlotSelectionController(self)
        # Initialize format service
        self.format_service = FormatService()
        # Initialize table controller
        self.table_controller = TableController(self)
        # Initialize text controller
        self.text_controller = TextController(self)
        # Initialize document service
        self.document_service = DocumentService(self)
        
        self.gui = PWLEditorGeometry(root, callback_handler=self)
        self.widgets = self.gui.get_all_widgets()

        # Ensure export formatting dropdown reflects a known default
        try:
            self.text_controller.initialize_export_format_default()
        except Exception:
            # Non-fatal during startup; status messaging will surface if used
            pass
        
        self.update_title()
        self.update_plot()
        if 'parse_status_var' in self.widgets:
            self.widgets['parse_status_var'].set("No data")
        
        # Ensure plot events are connected if starting in Table mode
        try:
            current_tab = self.notebook.tab(self.notebook.select(), 'text')
            if current_tab == 'Table':
                self.connect_plot_events()
        except Exception:
            pass
        
        # Save initial empty state as baseline
        self.undo_manager.save_state(self.pwl_data, "Initial state")
    
    @property
    def table(self):
        return self.gui.table
    
    @property 
    def text_editor(self):
        return self.gui.text_editor
    
    @property
    def status_var(self):
        return self.gui.status_var
    
    @property
    def parse_status_var(self):
        return self.gui.parse_status_var
    
    def get_examples_dir(self):
        """Get examples directory path for file dialogs"""
        # Delegate to service to avoid duplication
        return self.file_service.get_examples_dir()
    
    def get_initial_dir(self):
        """Get initial directory for file dialogs - remember last used or default to examples"""
        # Keep backward compatibility with existing last_directory state
        if self.last_directory:
            return self.last_directory
        return self.file_service.get_initial_dir()

    def show_about_dialog(self):
        """Display an About dialog with build metadata."""
        info = get_version_info()
        version = info.get('version', get_version())
        build_date = info.get('build_date', "")
        repo_url = info.get('repo_url', "")

        lines = [f"PWL Editor v{version}"]
        if build_date:
            lines.append(f"Build date: {build_date}")
        if repo_url:
            lines.append("")
            lines.append(repo_url)

        messagebox.showinfo("About PWL Editor", "\n".join(lines))
    
    @property
    def export_format_var(self):
        return self.gui.export_format_var
    
    @property
    def ax(self):
        return self.gui.ax
    
    @property
    def canvas(self):
        return self.gui.canvas
    
    @property
    def notebook(self):
        return self.gui.notebook

    def on_tab_changed(self, event):
        selected_tab = self.notebook.select()
        tab_text = self.notebook.tab(selected_tab, 'text')
        
        if tab_text == 'Table':
            self.text_to_table()
            # Connect plot selection events when entering Table mode
            self.connect_plot_events()
        elif tab_text == 'Text':
            # Disconnect plot events when leaving Table mode
            self.disconnect_plot_events()
            # Clear table selection when switching to text to avoid issues
            self.table.selection_remove(self.table.selection())
            # Clear plot highlighting
            self._update_plot_internal(None)
            self.table_to_text()

    def table_to_text(self):
        return self.text_controller.table_to_text()

    def text_to_table(self):
        return self.text_controller.text_to_table()

    def update_table(self):
        for item in self.table.get_children():
            self.table.delete(item)
        
        for i in range(self.pwl_data.get_point_count()):
            point_detail = self.pwl_data.get_point_detailed(i)
            if point_detail:
                abs_time = point_detail['absolute_time']
                value = point_detail['value']
                is_relative = point_detail['is_relative']
                time_type = "REL" if is_relative else "ABS"
                
                # Get the actual point to access original strings
                point = self.pwl_data.points[i]
                
                # Use original text strings directly (new string-based approach)
                time_display = point.time_str
                value_display = point.value_str
                
                self.table.insert('', tk.END, values=(
                    i+1, 
                    time_display, 
                    value_display,
                    time_type
                ))
        
        self.status_var.set(f"Loaded {self.pwl_data.get_point_count()} points")

    def on_table_select(self, event=None):
        """Delegate to TableController"""
        return self.table_controller.on_table_select(event)

    def _smart_time_format(self, time_value, reference_point=None):
        """Delegate to FormatService to preserve style from a reference when available."""
        return self.format_service.format_time(time_value, reference_point)

    def _smart_value_format(self, value, reference_point=None):
        """Delegate to FormatService to preserve style from a reference when available."""
        return self.format_service.format_value(value, reference_point)

    def _get_selected_point_indices(self) -> list[int]:
        try:
            selected_items = self.table.selection()
        except Exception:
            return []
        if not selected_items:
            return []
        children = self.table.get_children()
        indices: list[int] = []
        for item in selected_items:
            if item in children:
                indices.append(children.index(item))
        indices.sort()
        return indices

    def select_all_points(self, event=None):
        """Select all rows in the table view."""
        try:
            children = self.table.get_children()
        except Exception:
            return "break"
        if not children:
            return "break"
        self.table.selection_set(children)
        self.table.focus(children[0])
        return "break"

    def _reselect_table_indices(self, indices: list[int]):
        if not indices:
            return
        try:
            children = self.table.get_children()
            items = [children[i] for i in indices if 0 <= i < len(children)]
            if items:
                self.table.selection_set(items)
                self.table.focus(items[0])
        except Exception:
            pass

    def _apply_time_representation(
        self,
        pwl_data: PwlData,
        index: int,
        *,
        make_relative: bool,
        allow_first_point_relative: bool = False,
        reference_time_str: str | None = None,
        absolute_times: Sequence[float] | None = None,
    ) -> bool:
        """Convert a single point to relative/absolute while mirroring existing formatting."""
        if index < 0 or index >= pwl_data.get_point_count():
            return False

        point = pwl_data.points[index]
        reference_str = reference_time_str if reference_time_str is not None else point.time_str
        reference_point = SimpleNamespace(time_str=reference_str)

        if make_relative:
            if index == 0 and not allow_first_point_relative:
                return False
            if absolute_times is not None:
                current_abs = absolute_times[index]
                previous_abs = absolute_times[index - 1] if index > 0 else 0.0
            else:
                current_abs = pwl_data.get_absolute_time(index)
                previous_abs = pwl_data.get_absolute_time(index - 1) if index > 0 else 0.0
            delta = current_abs - previous_abs
            formatted_time = self.format_service.format_time(delta, reference_point)
            point.update_time_str(formatted_time)
            point.is_relative = True
        else:
            if absolute_times is not None:
                current_abs = absolute_times[index]
            else:
                current_abs = pwl_data.get_absolute_time(index)
            formatted_time = self.format_service.format_time(current_abs, reference_point)
            point.update_time_str(formatted_time)
            point.is_relative = False

        return True
    
    def update_plot(self, selected_indices=None):
        """Update plot and create undo point"""
        # Don't create undo points during undo/redo operations
        if getattr(self, '_undo_in_progress', False):
            self._update_plot_internal(selected_indices)
            return
        
        # Save undo point BEFORE updating (captures previous state)
        if hasattr(self, 'undo_manager'):
            description = getattr(self, '_operation_description', 'Edit')
            self.undo_manager.save_state(self.pwl_data, description)
            self._operation_description = ""  # Reset description
        
        self._update_plot_internal(selected_indices)

    def _update_plot_internal(self, selected_indices=None):
        """Internal plot update without undo point creation"""
        # Clear plot (this also removes any existing patches)
        self.ax.clear()
        # Any previously stored selection rectangle reference is now invalid.
        # Ask controller to clear it to keep internal/editor state in sync.
        try:
            self.plot_controller.clear_selection_rect()
        except Exception:
            # Fallback to clearing the attribute if controller isn't available
            self.selection_rect = None
        
        if self.pwl_data.get_point_count() > 0:
            times = self.pwl_data.timestamps
            values = self.pwl_data.values
            
            if len(times) > 0:
                plot_times = []
                plot_values = []
                
                i = 0
                while i < len(times):
                    current_time = times[i]
                    current_value = values[i]
                    
                    plot_times.append(current_time)
                    plot_values.append(current_value)
                    
                    j = i + 1
                    while j < len(times) and abs(times[j] - current_time) < 1e-12:
                        plot_times.append(current_time)
                        plot_values.append(values[j])
                        j += 1
                    
                    i = j
                
                self.ax.plot(plot_times, plot_values, 'bo-', markersize=4, linewidth=1.5)
                self.ax.plot(times, values, 'ro', markersize=6, alpha=0.7)
                
                # Highlight selected points if specified
                if selected_indices is not None and len(selected_indices) > 0:
                    selected_times = []
                    selected_values = []
                    for index in selected_indices:
                        if 0 <= index < len(times):
                            selected_times.append(times[index])
                            selected_values.append(values[index])
                    
                    if selected_times:
                        self.ax.plot(
                            selected_times,
                            selected_values,
                            'yo',
                            markersize=10,
                            markeredgecolor='red',
                            markeredgewidth=2,
                            alpha=0.8,
                        )
            
            if len(times) > 0:
                time_margin = (max(times) - min(times)) * 0.05 if len(times) > 1 else 0.1
                value_margin = (max(values) - min(values)) * 0.05 if len(values) > 1 else 0.1
                
                self.ax.set_xlim(min(times) - time_margin, max(times) + time_margin)
                self.ax.set_ylim(min(values) - value_margin, max(values) + value_margin)
        
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Value')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_title(f'PWL Waveform ({self.pwl_data.get_point_count()} points)')
        
        self.canvas.draw()

    def data_to_pixel(self, data_x, data_y):
        """Convert data coordinates to pixel coordinates"""
        try:
            if not self.ax or self.pwl_data.get_point_count() == 0:
                return None, None
            return util_data_to_pixel(self.ax, data_x, data_y)
        except Exception:
            return None, None

    def pixel_to_data(self, pixel_x, pixel_y):
        """Convert pixel coordinates to data coordinates"""
        try:
            if not self.ax or self.pwl_data.get_point_count() == 0:
                return None, None
            return util_pixel_to_data(self.ax, pixel_x, pixel_y)
        except Exception:
            return None, None

    def _clamp_pixel_to_axes(self, px, py):
        """Clamp pixel coordinates to the axes bounding box to support border drags."""
        try:
            return util_clamp(self.ax, px, py)
        except Exception:
            return px, py

    def on_plot_press(self, event):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.on_plot_press(event)

    def on_plot_motion(self, event):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.on_plot_motion(event)

    def on_plot_release(self, event):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.on_plot_release(event)

    def connect_plot_events(self):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.connect_plot_events()

    def disconnect_plot_events(self):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.disconnect_plot_events()

    def find_nearest_point(self, pixel_x, pixel_y):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.find_nearest_point(pixel_x, pixel_y)

    def find_points_in_box(self, start_data, end_data):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.find_points_in_box(start_data, end_data)

    def update_selection_rectangle(self, start_pixel, end_pixel):
        """Delegate to PlotSelectionController"""
        return self.plot_controller.update_selection_rectangle(start_pixel, end_pixel)

    def undo(self):
        """Undo last operation with comprehensive error handling and invalid text handling"""
        try:
            # First check if current text editor content is invalid
            current_text = self.text_editor.get(1.0, tk.END).strip()
            temp_data = PwlData()
            
            # If current text is invalid, just restore current valid state (don't consume undo point)
            if current_text and not temp_data.load_from_text(current_text):
                self.table_to_text()  # Sync text editor with current valid data
                self.status_var.set("Invalid text discarded - restored to last valid state")
                return
            
            # Current text is valid (or empty) - proceed with normal undo
            # Check if undo is possible
            if not hasattr(self, 'undo_manager') or not self.undo_manager.can_undo():
                self.status_var.set("Nothing to undo")
                return
            
            # Get preview of what will be undone
            undo_description = self.undo_manager.get_undo_description()
            
            # Perform undo
            self._undo_in_progress = True
            previous_data, description = self.undo_manager.undo()
            
            if previous_data is not None:
                # Store current selection to potentially restore
                current_selection = list(self.table.selection()) if hasattr(self, 'table') else []
                
                # Update data
                self.pwl_data = previous_data
                
                # Update all views
                self.update_table()
                self.table_to_text()  # Sync text editor
                self._update_plot_internal()  # Update plot without new undo point
                
                # Try to restore selection if items still exist
                if current_selection and self.pwl_data.get_point_count() > 0:
                    try:
                        for item_id in current_selection:
                            if self.table.exists(item_id):
                                self.table.selection_add(item_id)
                    except:
                        pass  # Selection restoration is optional
                
                self.mark_unsaved()
                self.status_var.set(f"Undone: {undo_description}")
            else:
                self.status_var.set("Undo failed - no previous state")
                
        except Exception as e:
            self.status_var.set(f"Undo error: {str(e)[:30]}...")
        finally:
            self._undo_in_progress = False

    def redo(self):
        """Redo next operation with comprehensive error handling"""
        try:
            # Check if redo is possible
            if not hasattr(self, 'undo_manager') or not self.undo_manager.can_redo():
                self.status_var.set("Nothing to redo")
                return
            
            # Get preview of what will be redone
            redo_description = self.undo_manager.get_redo_description()
            
            # Perform redo
            self._undo_in_progress = True
            next_data, description = self.undo_manager.redo()
            
            if next_data is not None:
                # Store current selection to potentially restore
                current_selection = list(self.table.selection()) if hasattr(self, 'table') else []
                
                # Update data
                self.pwl_data = next_data
                
                # Update all views
                self.update_table()
                self.table_to_text()  # Sync text editor
                self._update_plot_internal()  # Update plot without new undo point
                
                # Try to restore selection if items still exist
                if current_selection and self.pwl_data.get_point_count() > 0:
                    try:
                        for item_id in current_selection:
                            if self.table.exists(item_id):
                                self.table.selection_add(item_id)
                    except:
                        pass  # Selection restoration is optional
                
                self.mark_unsaved()
                self.status_var.set(f"Redone: {redo_description}")
            else:
                self.status_var.set("Redo failed - invalid state")
                
        except Exception as e:
            self.status_var.set(f"Redo error: {str(e)[:30]}...")
        finally:
            self._undo_in_progress = False

    def add_point_above(self):
        """Add point above selected row with smart defaults"""
        self._operation_description = "Add point above"
        selected = self.table.selection()
        if selected:
            item = selected[0]
            values = self.table.item(item, 'values')
            index = int(values[0]) - 1
            
            current_point = self.pwl_data.points[index]
            prev_point = self.pwl_data.points[index - 1] if index > 0 else None
            
            # Use smart time calculation
            new_time_str = self.smart_insertion.calculate_time_above(current_point, prev_point)
            new_value_str = current_point.value_str  # Keep same value
            
            # Create new point with smart timing
            new_point = PwlPoint(new_time_str, new_value_str, is_relative=current_point.is_relative)
            self.pwl_data.points.insert(index, new_point)
            
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()
            
            # Update status with helpful info
            reference_info = f"between {prev_point.time_str} and {current_point.time_str}" if prev_point else f"before {current_point.time_str}"
            self.status_var.set(f"Added point at {new_time_str} ({reference_info})")
            
            # Keep selection on the newly inserted point
            if index < len(self.table.get_children()):
                self.table.selection_set(self.table.get_children()[index])
        else:
            # No selection - add at beginning with smart timing
            if self.pwl_data.get_point_count() > 0:
                first_point = self.pwl_data.points[0]
                new_time_str = self.smart_insertion.calculate_time_above(first_point)
                new_value_str = first_point.value_str
                new_point = PwlPoint(new_time_str, new_value_str, is_relative=False)
            else:
                # Empty list - use defaults
                time_str, value_str = self.smart_insertion.get_empty_list_defaults()
                new_point = PwlPoint(time_str, value_str, is_relative=False)
            
            self.pwl_data.points.insert(0, new_point)
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()

    def add_point_below(self):
        """Add point below selected row with smart defaults"""
        self._operation_description = "Add point below"
        selected = self.table.selection()
        if selected:
            # Get selected item details
            item = selected[0]
            values = self.table.item(item, 'values')
            index = int(values[0]) - 1
            
            current_point = self.pwl_data.points[index]
            next_point = self.pwl_data.points[index + 1] if index < len(self.pwl_data.points) - 1 else None
            
            # Use smart insertion calculation
            new_time_str = self.smart_insertion.calculate_time_below(current_point, next_point)
            new_value_str = current_point.value_str  # Keep same value
            
            # Create new point with smart timing
            new_point = PwlPoint(new_time_str, new_value_str, is_relative=current_point.is_relative)
            self.pwl_data.points.insert(index + 1, new_point)
            
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()
            
            # Update status with helpful info
            self.status_var.set(f"Added point at {new_time_str} (preserving {current_point.time_str} notation)")
        else:
            # No selection - add at end with smart timing
            if self.pwl_data.get_point_count() > 0:
                last_point = self.pwl_data.points[-1]
                new_time_str = self.smart_insertion.get_empty_list_next(last_point)
                new_value_str = last_point.value_str
                new_point = PwlPoint(new_time_str, new_value_str, is_relative=False)
            else:
                # Empty list - use defaults
                time_str, value_str = self.smart_insertion.get_empty_list_defaults()
                new_point = PwlPoint(time_str, value_str, is_relative=False)
            
            self.pwl_data.points.append(new_point)
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()

    def start_inline_edit(self, event):
        # Check if we should restore previous multi-selection for editing
        current_selection = list(self.table.selection())
        
        # If we have a previous selection with multiple items, and current selection is single item,
        # this might be a double-click on a multi-selection - restore the previous selection
        if (self.previous_selection and len(self.previous_selection) > 1 and 
            len(current_selection) == 1 and current_selection[0] in self.previous_selection):
            
            # Restore previous multi-selection
            self.table.selection_remove(self.table.selection())
            prev_sel = list(self.previous_selection) if self.previous_selection else []
            for item in prev_sel:
                try:
                    self.table.selection_add(item)
                except:
                    pass
            selected_items = prev_sel
            # Clear previous_selection after using it to prevent confusion in next cycle
            self.previous_selection = None
        else:
            selected_items = current_selection
        
        if not selected_items:
            return
        
        # Use the clicked item for positioning, but work with all selected items
        clicked_item = self.table.identify_row(event.y)
        if not clicked_item:
            # If we can't identify clicked item, use the first selected item
            clicked_item = selected_items[0]
        
        column = self.table.identify_column(event.x)
        if column not in ['#2', '#3', '#4']:
            return
        
        bbox = self.table.bbox(clicked_item, column)
        if not bbox:
            return
        
        current_value = self.table.item(clicked_item, 'values')[int(column[1:]) - 1]
        
        self.edit_item = clicked_item
        self.edit_column = column
        self.edit_selected_items = selected_items  # Store all selected items
        
        # Show feedback for multiple selection
        if len(selected_items) > 1:
            feedback_text = f"Editing {len(selected_items)} rows"
            # You can add a temporary label here if desired
        
        if column == '#4':
            # Use a deterministic popup menu instead of a Combobox to avoid preselection issues
            popup = tk.Menu(self.root, tearoff=0)
            popup.add_command(
                label='ABS',
                command=lambda: self.apply_type_to_selected('ABS', selected_items)
            )
            popup.add_command(
                label='REL',
                command=lambda: self.apply_type_to_selected('REL', selected_items)
            )
            # Show the menu just below the edited cell
            x = self.table.winfo_rootx() + bbox[0]
            y = self.table.winfo_rooty() + bbox[1] + bbox[3]
            try:
                popup.tk_popup(x, y)
            finally:
                popup.grab_release()
            return
        else:
            self.edit_entry = tk.Entry(self.table)
            self.edit_entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
            self.edit_entry.insert(0, current_value)
            self.edit_entry.select_range(0, tk.END)
            self.edit_entry.focus()
            
            self.edit_entry.bind('<Return>', self.finish_inline_edit)
            self.edit_entry.bind('<Escape>', self.cancel_inline_edit)
            self.edit_entry.bind('<FocusOut>', self.finish_inline_edit)
            
            self.edit_combo = None

    def on_combo_click(self, event):
        """Handle combobox click - simple approach to detect selection"""
        try:
            if self.edit_combo:
                # Use a short delay to check if ComboboxSelected fired
                # If not, assume user clicked on already selected item
                self.combo_click_value = self.edit_combo.get()
                self.combo_selection_happened = False
                
                # Schedule a check after potential ComboboxSelected event
                self.root.after(100, self.check_combo_click_result)
                
        except Exception:
            pass
    
    def check_combo_click_result(self):
        """Check if combo click resulted in selection or not"""
        try:
            if (self.edit_combo and hasattr(self, 'combo_click_value') and 
                not getattr(self, 'combo_selection_happened', True)):
                # No ComboboxSelected event fired, but user clicked
                # This means they clicked on already selected item
                if self.edit_combo.get() == self.combo_click_value:
                    # Finish editing with the same value
                    self.finish_inline_edit()
        except Exception:
            pass
        finally:
            # Clean up temporary attributes
            if hasattr(self, 'combo_click_value'):
                delattr(self, 'combo_click_value')
            if hasattr(self, 'combo_selection_happened'):
                delattr(self, 'combo_selection_happened')

    def on_combo_escape(self, event):
        """Handle escape key for combobox - always cancel"""
        # Force cancel editing immediately
        if self.edit_combo:
            self.edit_combo.destroy()
            self.edit_combo = None
        self.cancel_inline_edit()
        return 'break'  # Prevent further event processing

    def on_combo_focus_out(self, event):
        """Handle combobox focus out - only finish edit if not clicking dropdown"""
        try:
            # Check if the focus is going to the combobox's dropdown listbox
            # If so, don't finish editing yet
            focused_widget = self.root.focus_get()
            
            # If focus is going to a listbox (dropdown), don't finish editing
            if focused_widget and 'listbox' in str(focused_widget).lower():
                return
            
            # If focus is going to the combobox itself, don't finish editing
            if focused_widget == self.edit_combo:
                return
            
            # Otherwise, finish editing
            self.finish_inline_edit()
            
        except Exception:
            # If anything goes wrong, just finish editing
            self.finish_inline_edit()

    def _restore_selection(self, selected_items):
        """Helper method to restore table selection"""
        try:
            # Clear current selection
            self.table.selection_remove(self.table.selection())
            # Restore the original selection
            for item in selected_items:
                self.table.selection_add(item)
        except Exception:
            # Fail silently if selection restoration fails
            pass

    def finish_inline_edit(self, event=None):
        """Finish inline editing and update data"""
        if not (self.edit_entry or self.edit_combo) or not self.edit_item:
            return
        
        # Mark that ComboboxSelected event fired
        if hasattr(self, 'combo_click_value'):
            self.combo_selection_happened = True
        
        try:
            # Get the new value from appropriate widget
            if self.edit_entry:
                new_value = self.edit_entry.get().strip()
                if not new_value:
                    self.cancel_inline_edit()
                    return
            elif self.edit_combo:
                new_value = self.edit_combo.get()
            else:
                return
            
            # Get all selected items (or just the edited one if edit_selected_items doesn't exist)
            selected_items = getattr(self, 'edit_selected_items', [self.edit_item])
            
            # Process each selected item
            for item in selected_items:
                # Get item index
                values = self.table.item(item, 'values')
                index = int(values[0]) - 1  # Convert to 0-based index
                
                # Update the appropriate field
                if self.edit_column == '#2':  # Time column
                    # Update time as string directly
                    self.pwl_data.points[index].update_time_str(new_value)
                elif self.edit_column == '#3':  # Value column
                    # Update value as string directly
                    self.pwl_data.points[index].update_value_str(new_value)
                elif self.edit_column == '#4':  # Type column
                    # Smart format conversion that preserves waveform
                    is_relative = (new_value == 'REL')
                    current_point = self.pwl_data.points[index]
                    
                    if current_point.is_relative != is_relative:
                        original_time_str = current_point.time_str
                        converted = self._apply_time_representation(
                            self.pwl_data,
                            index,
                            make_relative=is_relative,
                            reference_time_str=original_time_str,
                        )
                        if not converted:
                            if len(selected_items) == 1:
                                messagebox.showwarning(
                                    "Invalid Conversion",
                                    "First point cannot be relative time. Keeping as absolute.",
                                )
                            continue
            
            # Clean up edit widgets
            if self.edit_entry:
                self.edit_entry.destroy()
                self.edit_entry = None
            if self.edit_combo:
                self.edit_combo.destroy()
                self.edit_combo = None
            self.edit_item = None
            self.edit_selected_items = None
            # Clear any preserved selection state to prevent confusion
            self.previous_selection = None
            
            # Set operation description based on what was edited
            if self.edit_column:
                column_name = self.table.heading(self.edit_column)['text']
                count = len(selected_items)
                if count == 1:
                    self._operation_description = f"Edit {column_name.lower()}"
                else:
                    self._operation_description = f"Edit {column_name.lower()} ({count} points)"
            else:
                self._operation_description = "Edit value"
            
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()
            
        except Exception as e:
            messagebox.showerror("Edit Error", f"Invalid value: {e}")
            self.cancel_inline_edit()

    def apply_type_to_selected(self, new_value, selected_items):
        """Apply ABS/REL type to all selected rows deterministically (popup menu handler)."""
        try:
            # Update internal state to mimic an edit on column #4
            self.edit_column = '#4'
            self.edit_item = selected_items[0] if selected_items else None
            self.edit_selected_items = selected_items

            # Perform the same conversion logic as finish_inline_edit would
            for item in selected_items:
                values = self.table.item(item, 'values')
                index = int(values[0]) - 1
                is_relative = (new_value == 'REL')
                current_point = self.pwl_data.points[index]

                if current_point.is_relative != is_relative:
                    original_time_str = current_point.time_str
                    converted = self._apply_time_representation(
                        self.pwl_data,
                        index,
                        make_relative=is_relative,
                        reference_time_str=original_time_str,
                    )
                    if not converted:
                        if len(selected_items) == 1:
                            messagebox.showwarning(
                                "Invalid Conversion",
                                "First point cannot be relative time. Keeping as absolute.",
                            )
                        continue

            # Cleanup any active editors
            if self.edit_entry:
                self.edit_entry.destroy()
                self.edit_entry = None
            if self.edit_combo:
                self.edit_combo.destroy()
                self.edit_combo = None
            self.edit_item = None
            self.edit_selected_items = None
            self.previous_selection = None

            # Refresh UI
            self.update_table()
            self.update_plot()
            self.table_to_text()
            self.mark_unsaved()

        except Exception as e:
            messagebox.showerror("Type Edit Error", f"Failed to apply type: {e}")

    def cancel_inline_edit(self, event=None):
        """Cancel inline editing"""
        # Clean up any combo click tracking
        if hasattr(self, 'combo_click_value'):
            delattr(self, 'combo_click_value')
        if hasattr(self, 'combo_selection_happened'):
            delattr(self, 'combo_selection_happened')
                
        if self.edit_entry:
            self.edit_entry.destroy()
            self.edit_entry = None
        if self.edit_combo:
            self.edit_combo.destroy()
            self.edit_combo = None
        self.edit_item = None
        self.edit_selected_items = None
        # Clear any preserved selection state to prevent confusion
        self.previous_selection = None

    def remove_selected(self, event=None):
        """Remove selected point from table"""
        selected_items = self.table.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select a point to remove")
            return
        
        # Set operation description based on number of items
        count = len(selected_items)
        self._operation_description = f"Remove {count} point{'s' if count > 1 else ''}"
        
        indices_to_remove = []
        for item in selected_items:
            values = self.table.item(item, 'values')
            if values:
                indices_to_remove.append(int(values[0]) - 1)  # Convert to 0-based index
        
        # Remove in reverse order
        for index in sorted(indices_to_remove, reverse=True):
            self.pwl_data.remove_point(index)
        
        # Update views
        self.update_table()
        self.update_plot()
        self.mark_unsaved()

    def move_point_up(self):
        """Move selected points up in the table"""
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select point(s) to move")
            return
        
        # Get indices of selected items
        indices = []
        for item in selected:
            values = self.table.item(item, 'values')
            if values:
                indices.append(int(values[0]) - 1)  # Convert to 0-based index
        
        # Sort indices to process from top to bottom
        indices.sort()
        
        # Check if we can move all selected points up
        if indices[0] <= 0:
            messagebox.showinfo("Cannot Move", "Cannot move selection up - already at top")
            return
        
        # Move all selected points up by one position
        for i in indices:
            self.pwl_data.swap_points(i, i - 1)
        
        self.update_table()
        self.update_plot()
        self.mark_unsaved()
        
        # Re-select the moved items
        for i in indices:
            if i - 1 >= 0:
                self.table.selection_add(self.table.get_children()[i - 1])

    def move_point_down(self):
        """Move selected points down in the table"""
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select point(s) to move")
            return
        
        # Get indices of selected items
        indices = []
        for item in selected:
            values = self.table.item(item, 'values')
            if values:
                indices.append(int(values[0]) - 1)  # Convert to 0-based index
        
        # Sort indices to process from bottom to top
        indices.sort(reverse=True)
        
        # Check if we can move all selected points down
        if indices[0] >= self.pwl_data.get_point_count() - 1:
            messagebox.showinfo("Cannot Move", "Cannot move selection down - already at bottom")
            return
        
        # Move all selected points down by one position
        for i in indices:
            self.pwl_data.swap_points(i, i + 1)
        
        self.update_table()
        self.update_plot()
        self.mark_unsaved()
        
        # Re-select the moved items
        for i in sorted(indices):
            if i + 1 < len(self.table.get_children()):
                self.table.selection_add(self.table.get_children()[i + 1])

    def on_export_format_changed(self, event=None):
        return self.text_controller.on_export_format_changed(event)
    
    def table_to_text_with_format(self):
        return self.text_controller.table_to_text_with_format()
    
    def _get_formatted_content_for_save(self, apply_export_format: bool = True):
        return self.text_controller.get_formatted_content_for_save(apply_export_format=apply_export_format)

    def generate_square_wave(self):
        """Open the square wave generator dialog and merge the result if applied."""
        try:
            from dialogs.square_wave_dialog import SquareWaveGeneratorDialog
        except ImportError as exc:
            messagebox.showerror("Generate Square Wave", f"Failed to load generator dialog: {exc}")
            return

        dialog = SquareWaveGeneratorDialog(self)
        generated_data = dialog.show()
        if generated_data is None:
            return

        self._operation_description = "Generate square wave"
        self.pwl_data = generated_data
        self.update_table()
        self.table_to_text_with_format()
        self.update_plot()
        self.mark_unsaved()

    def generate_triangle_wave(self):
        """Open the triangle wave generator dialog and merge the result if applied."""
        try:
            from dialogs.triangle_wave_dialog import TriangleWaveGeneratorDialog
        except ImportError as exc:
            messagebox.showerror("Generate Triangle Wave", f"Failed to load generator dialog: {exc}")
            return

        dialog = TriangleWaveGeneratorDialog(self)
        generated_data = dialog.show()
        if generated_data is None:
            return

        self._operation_description = "Generate triangle wave"
        self.pwl_data = generated_data
        self.update_table()
        self.table_to_text_with_format()
        self.update_plot()
        self.mark_unsaved()

    def generate_saw_wave(self):
        """Open the saw wave generator dialog and merge the result if applied."""
        try:
            from dialogs.saw_wave_dialog import SawWaveGeneratorDialog
        except ImportError as exc:
            messagebox.showerror("Generate Saw Wave", f"Failed to load generator dialog: {exc}")
            return

        dialog = SawWaveGeneratorDialog(self)
        generated_data = dialog.show()
        if generated_data is None:
            return

        self._operation_description = "Generate saw wave"
        self.pwl_data = generated_data
        self.update_table()
        self.table_to_text_with_format()
        self.update_plot()
        self.mark_unsaved()

    def repair_waveform(self):
        """Open the waveform repair dialog and apply fixes if requested."""
        if self.pwl_data.get_point_count() == 0:
            messagebox.showinfo("Repair Waveform", "No waveform data to repair.")
            return

        try:
            from dialogs.waveform_repair_dialog import WaveformRepairDialog
        except ImportError as exc:
            messagebox.showerror("Repair Waveform", f"Failed to load repair dialog: {exc}")
            return

        dialog = WaveformRepairDialog(self)
        repaired_data = dialog.show()
        if not repaired_data:
            # Dialog already restored original data/state when cancelling or when no repair was needed
            return

        self._operation_description = "Repair waveform"
        self.pwl_data = repaired_data
        self.update_table()
        self.table_to_text_with_format()
        self.update_plot()
        self.mark_unsaved()
        self.status_var.set("Waveform repaired successfully")

    def sort_data(self):
        """Sort data points by time"""
        if self.pwl_data.get_point_count() > 0:
            # Data is automatically sorted when added, but this forces a resort
            self.pwl_data._sort_by_time()
            self.update_table()
            self.update_plot()
            self.mark_unsaved()
            self.status_var.set("Data sorted by time")

    def clear_all(self):
        """Clear all data"""
        if self.pwl_data.get_point_count() > 0:
            if messagebox.askyesno("Clear All", "Are you sure you want to clear all data?"):
                self.pwl_data.clear()
                self.update_table()
                self.update_plot()
                self.table_to_text()
                self.mark_unsaved()
                self.status_var.set("All data cleared")

    def _format_si_prefix(self, value):
        """Use shared SI formatting."""
        return self.format_service.format_si(value)
    
    def _format_scientific(self, value):
        """Use shared engineering-style scientific formatting."""
        return self.format_service.format_engineering(value)

    def convert_time_to_si(self):
        """Convert time values to SI prefix notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    si_str = self._format_si_prefix(time_val)
                    point.update_time_str(si_str)
                    converted += 1

            if converted == 0:
                self.status_var.set("No time values converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted time to SI prefix for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("Time values converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting time to SI: {e}")

    def convert_time_to_scientific(self):
        """Convert time values to scientific notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    sci_str = self._format_scientific(time_val)
                    point.update_time_str(sci_str)
                    converted += 1

            if converted == 0:
                self.status_var.set("No time values converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted time to scientific notation for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("Time values converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting time to scientific: {e}")

    def convert_value_to_si(self):
        """Convert value data to SI prefix notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    si_str = self._format_si_prefix(value_val)
                    point.update_value_str(si_str)
                    converted += 1

            if converted == 0:
                self.status_var.set("No values converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted values to SI prefix for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("Values converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting values to SI: {e}")

    def convert_value_to_scientific(self):
        """Convert value data to scientific notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    sci_str = self._format_scientific(value_val)
                    point.update_value_str(sci_str)
                    converted += 1

            if converted == 0:
                self.status_var.set("No values converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted values to scientific notation for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("Values converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting values to scientific: {e}")

    def convert_all_to_si(self):
        """Convert time and values to SI prefix notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    point.update_time_str(self._format_si_prefix(time_val))
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    point.update_value_str(self._format_si_prefix(value_val))
                converted += 1

            if converted == 0:
                self.status_var.set("No points converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted SI prefix for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("All data converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting to SI: {e}")

    def convert_all_to_scientific(self):
        """Convert time and values to scientific notation (selection-aware)."""
        try:
            selection = self._get_selected_point_indices()
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            targets = selection if selection else list(range(point_count))
            converted = 0
            for index in targets:
                point = self.pwl_data.points[index]
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    point.update_time_str(self._format_scientific(time_val))
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    point.update_value_str(self._format_scientific(value_val))
                converted += 1
            
            if converted == 0:
                self.status_var.set("No points converted")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection if selection else None)
            self.mark_unsaved()
            if selection:
                self.status_var.set(f"Converted scientific notation for {converted} selected point{'s' if converted != 1 else ''}")
            else:
                self.status_var.set("All data converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting all to scientific: {e}")

    def new_file(self):
        """Create new file - delegate to DocumentService"""
        return self.document_service.new_file()

    def open_file(self):
        """Open PWL file - delegate to DocumentService"""
        return self.document_service.open_file()

    def save_file(self):
        """Save current file with confirmation - delegate to DocumentService"""
        return self.document_service.save_file()

    def save_file_as(self):
        """Save file with new name - delegate to DocumentService"""
        return self.document_service.save_file_as()

    def export_file(self):
        """Export current data without changing the active document."""
        return self.document_service.export_file()

    def on_text_changed(self, event):
        """Handle text editor changes with real-time validation"""
        self.mark_unsaved()
        
        # Cancel any pending validation
        if hasattr(self, 'validation_after_id'):
            self.root.after_cancel(self.validation_after_id)
        
        # Schedule validation after 500ms of no typing
        self.validation_after_id = self.root.after(500, self.validate_text_content)

    def validate_text_content(self):
        """Validate text content and update status"""
        try:
            text_content = self.text_editor.get(1.0, tk.END).strip()
            if not text_content:
                self.parse_status_var.set("Empty text")
                return
            
            # Try to parse the text content
            temp_pwl_data = PwlData()
            if temp_pwl_data.load_from_text(text_content):
                point_count = temp_pwl_data.get_point_count()
                self.parse_status_var.set(f"✓ Valid - {point_count} points")
                
                # Update plot in real-time if text is valid
                self.pwl_data = temp_pwl_data
                self.update_plot()
                self.update_table()
            else:
                self.parse_status_var.set("⚠ Invalid PWL syntax")
                
        except Exception as e:
            self.parse_status_var.set(f"⚠ Error: {str(e)[:20]}...")

    def convert_to_relative(self):
        """Convert the entire dataset to relative time format."""
        self._operation_description = "Convert to relative time"
        try:
            point_count = self.pwl_data.get_point_count()
            if point_count <= 1:
                self.status_var.set("Not enough points to convert to relative time")
                return

            absolute_times = self.pwl_data.timestamps
            converted = 0

            # Ensure first point remains absolute without altering existing formatting
            first_point = self.pwl_data.points[0]
            first_point.is_relative = False

            for index in range(1, point_count):
                original_time = self.pwl_data.points[index].time_str
                if self._apply_time_representation(
                    self.pwl_data,
                    index,
                    make_relative=True,
                    reference_time_str=original_time,
                    absolute_times=absolute_times,
                ):
                    converted += 1

            if converted == 0:
                self.status_var.set("No points converted to relative time")
                return

            self.pwl_data.default_format = 'relative'
            self.update_table()
            self.table_to_text_with_format()
            self.update_plot()
            self.mark_unsaved()
            self.status_var.set("Converted all points to relative time format")
        except Exception as e:
            messagebox.showerror("Conversion Error", f"Failed to convert to relative time: {e}")

    def convert_to_absolute(self):
        """Convert the entire dataset to absolute time format."""
        self._operation_description = "Convert to absolute time"
        try:
            point_count = self.pwl_data.get_point_count()
            if point_count == 0:
                self.status_var.set("No data to convert")
                return

            absolute_times = self.pwl_data.timestamps
            converted = 0
            for index in range(point_count):
                original_time = self.pwl_data.points[index].time_str
                if self._apply_time_representation(
                    self.pwl_data,
                    index,
                    make_relative=False,
                    reference_time_str=original_time,
                    absolute_times=absolute_times,
                ):
                    converted += 1

            if converted == 0:
                self.status_var.set("No points converted to absolute time")
                return

            self.pwl_data.default_format = 'absolute'
            self.update_table()
            self.table_to_text_with_format()
            self.update_plot()
            self.mark_unsaved()
            self.status_var.set("Converted all points to absolute time format")
        except Exception as e:
            messagebox.showerror("Conversion Error", f"Failed to convert to absolute time: {e}")

    def convert_time_selection_to_relative(self):
        """Convert selected points to relative time; fallback to all when none selected."""
        selection = self._get_selected_point_indices()
        if not selection:
            self.convert_to_relative()
            return

        try:
            self._operation_description = "Convert selection to relative time"
            absolute_times = self.pwl_data.timestamps
            converted = 0
            skipped_first = False
            for index in selection:
                original_time = self.pwl_data.points[index].time_str
                if self._apply_time_representation(
                    self.pwl_data,
                    index,
                    make_relative=True,
                    reference_time_str=original_time,
                    absolute_times=absolute_times,
                ):
                    converted += 1
                elif index == 0:
                    skipped_first = True

            if converted == 0:
                message = "No points converted to relative time"
                if skipped_first:
                    message += " (first point must remain absolute)"
                self.status_var.set(message)
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection)
            self.mark_unsaved()

            message = f"Converted {converted} selected point{'s' if converted != 1 else ''} to relative time"
            if skipped_first:
                message += " (first point left absolute)"
            self.status_var.set(message)
        except Exception as e:
            self.status_var.set(f"Error converting selection to relative time: {e}")

    def convert_time_selection_to_absolute(self):
        """Convert selected points to absolute time; fallback to all when none selected."""
        selection = self._get_selected_point_indices()
        if not selection:
            self.convert_to_absolute()
            return

        try:
            self._operation_description = "Convert selection to absolute time"
            absolute_times = self.pwl_data.timestamps
            converted = 0
            for index in selection:
                original_time = self.pwl_data.points[index].time_str
                if self._apply_time_representation(
                    self.pwl_data,
                    index,
                    make_relative=False,
                    reference_time_str=original_time,
                    absolute_times=absolute_times,
                ):
                    converted += 1

            if converted == 0:
                self.status_var.set("No points converted to absolute time")
                return

            self.update_table()
            self._reselect_table_indices(selection)
            self.table_to_text_with_format()
            self.update_plot(selection)
            self.mark_unsaved()
            self.status_var.set(f"Converted {converted} selected point{'s' if converted != 1 else ''} to absolute time")
        except Exception as e:
            self.status_var.set(f"Error converting selection to absolute time: {e}")

    def mark_unsaved(self):
        """Mark file as having unsaved changes"""
        if not self.unsaved_changes:
            self.unsaved_changes = True
            self.update_title()

    def update_title(self):
        """Update window title"""
        title = f"PWL Editor v{get_version()}"
        if self.current_file:
            title += f" - {os.path.basename(self.current_file)}"
        if self.unsaved_changes:
            title += " *"
        self.root.title(title)

    def check_unsaved_changes(self):
        """Check for unsaved changes and prompt user"""
        if self.unsaved_changes:
            try:
                has_data = self.pwl_data.get_point_count() > 0
            except Exception:
                has_data = False

            text_dirty = False
            try:
                text_dirty = bool(self.text_editor.get(1.0, tk.END).strip())
            except Exception:
                pass

            if self.current_file is None and not has_data and not text_dirty:
                # Treat pristine startup state as clean even if a flag was toggled
                self.unsaved_changes = False
                return True

            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before continuing?"
            )
            if result is True:  # Save
                self.save_file()
                return not self.unsaved_changes  # Only continue if save was successful
            elif result is False:  # Don't save
                return True
            else:  # Cancel
                return False
        return True

    def on_closing(self):
        """Handle window closing"""
        if self.check_unsaved_changes():
            self.root.destroy()

def main():
    root = tk.Tk()
    app = PWLEditor(root)
    root.mainloop()

if __name__ == '__main__':
    main()
