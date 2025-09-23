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
from pwl_parser import PwlData, PwlPoint
from pwl_gui_geometry import PWLEditorGeometry
from pwl_insertion import SmartInsertion
from pwl_undo import UndoRedoManager
from version import get_version
from utils.plot_coordinates import data_to_pixel as util_data_to_pixel, pixel_to_data as util_pixel_to_data, clamp_pixel_to_axes as util_clamp
from services.file_service import FileService
from services.format_service import FormatService
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
                
                self.ax.plot(plot_times, plot_values, 'bo-', markersize=4, linewidth=1.5, label='PWL Points')
                self.ax.plot(times, values, 'ro', markersize=6, alpha=0.7, label='Data Points')
                
                # Highlight selected points if specified
                if selected_indices is not None and len(selected_indices) > 0:
                    selected_times = []
                    selected_values = []
                    for index in selected_indices:
                        if 0 <= index < len(times):
                            selected_times.append(times[index])
                            selected_values.append(values[index])
                    
                    if selected_times:
                        self.ax.plot(selected_times, selected_values, 'yo', markersize=10, 
                                   markeredgecolor='red', markeredgewidth=2, alpha=0.8, 
                                   label=f'Selected Points ({len(selected_times)})')
            
            self.ax.legend()
            
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
                        if is_relative:
                            # Converting ABS → REL: calculate delta and preserve format style
                            if index > 0:
                                prev_abs_time = self.pwl_data.get_absolute_time(index - 1)
                                curr_abs_time = self.pwl_data.get_absolute_time(index)
                                delta = curr_abs_time - prev_abs_time
                                
                                # Preserve the original notation style for delta
                                delta_str = self.format_service.format_time(delta, current_point)
                                current_point.update_time_str(delta_str)
                            else:
                                # First point can't be relative, skip this item
                                if len(selected_items) == 1:
                                    messagebox.showwarning("Invalid Conversion", 
                                                         "First point cannot be relative time. Keeping as absolute.")
                                continue
                        else:
                            # Converting REL → ABS: store absolute time preserving format style
                            abs_time = self.pwl_data.get_absolute_time(index)
                            abs_time_str = self.format_service.format_time(abs_time, current_point)
                            current_point.update_time_str(abs_time_str)
                        
                        current_point.is_relative = is_relative
            
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
                    if is_relative:
                        # Converting ABS → REL
                        if index > 0:
                            prev_abs_time = self.pwl_data.get_absolute_time(index - 1)
                            curr_abs_time = self.pwl_data.get_absolute_time(index)
                            delta = curr_abs_time - prev_abs_time
                            delta_str = self.format_service.format_time(delta, current_point)
                            current_point.update_time_str(delta_str)
                        else:
                            # First point cannot be relative
                            if len(selected_items) == 1:
                                messagebox.showwarning("Invalid Conversion", "First point cannot be relative time. Keeping as absolute.")
                            continue
                    else:
                        # Converting REL → ABS
                        abs_time = self.pwl_data.get_absolute_time(index)
                        abs_time_str = self.format_service.format_time(abs_time, current_point)
                        current_point.update_time_str(abs_time_str)

                    current_point.is_relative = is_relative

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
    
    def _get_formatted_content_for_save(self):
        return self.text_controller.get_formatted_content_for_save()

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
        """Convert time values to SI prefix notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'time_str') and point.time_str:
                    # Convert to proper SI prefix notation
                    time_val = point.get_time_value()
                    si_str = self._format_si_prefix(time_val)
                    point.update_time_str(si_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("Time values converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting time to SI: {e}")

    def convert_time_to_scientific(self):
        """Convert time values to scientific notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'time_str') and point.time_str:
                    # Convert to improved scientific notation
                    time_val = point.get_time_value()
                    sci_str = self._format_scientific(time_val)
                    point.update_time_str(sci_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("Time values converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting time to scientific: {e}")

    def convert_value_to_si(self):
        """Convert value data to SI prefix notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'value_str') and point.value_str:
                    # Convert to proper SI prefix notation
                    value_val = point.get_value_value()
                    si_str = self._format_si_prefix(value_val)
                    point.update_value_str(si_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("Values converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting values to SI: {e}")

    def convert_value_to_scientific(self):
        """Convert value data to scientific notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'value_str') and point.value_str:
                    # Convert to improved scientific notation
                    value_val = point.get_value_value()
                    sci_str = self._format_scientific(value_val)
                    point.update_value_str(sci_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("Values converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting values to scientific: {e}")

    def convert_all_to_si(self):
        """Convert all data (time and values) to SI prefix notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    si_str = self._format_si_prefix(time_val)
                    point.update_time_str(si_str)
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    si_str = self._format_si_prefix(value_val)
                    point.update_value_str(si_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("All data converted to SI prefix notation")
        except Exception as e:
            self.status_var.set(f"Error converting all to SI: {e}")

    def convert_all_to_scientific(self):
        """Convert all data (time and values) to scientific notation"""
        try:
            for point in self.pwl_data.points:
                if hasattr(point, 'time_str') and point.time_str:
                    time_val = point.get_time_value()
                    sci_str = self._format_scientific(time_val)
                    point.update_time_str(sci_str)
                if hasattr(point, 'value_str') and point.value_str:
                    value_val = point.get_value_value()
                    sci_str = self._format_scientific(value_val)
                    point.update_value_str(sci_str)
            
            self.update_table()
            self.table_to_text_with_format()
            self.mark_unsaved()
            self.status_var.set("All data converted to scientific notation")
        except Exception as e:
            self.status_var.set(f"Error converting all to scientific: {e}")

    def restore_original_formatting(self):
        """Restore original formatting from when the file was loaded"""
        try:
            # Restore from backup display strings if available
            restored_count = 0
            for point in self.pwl_data.points:
                if hasattr(point, 'display_time_str') and point.display_time_str:
                    point.original_time_str = point.display_time_str
                    delattr(point, 'display_time_str')
                    restored_count += 1
                if hasattr(point, 'display_value_str') and point.display_value_str:
                    point.original_value_str = point.display_value_str
                    delattr(point, 'display_value_str')
                    restored_count += 1
            
            if restored_count > 0:
                self.update_table()
                self.table_to_text_with_format()
                self.mark_unsaved()
                self.status_var.set("Original formatting restored")
            else:
                # If no backup available, reload from file
                if self.current_file:
                    if messagebox.askyesno("Restore Original", 
                        "No backup available. Reload file to restore original formatting? This will lose any unsaved changes."):
                        # Reload the current file
                        new_pwl_data = PwlData()
                        if new_pwl_data.load_from_file(self.current_file, 0.001):
                            self.pwl_data = new_pwl_data
                            self.update_table()
                            self.update_plot()
                            self.table_to_text()
                            self.unsaved_changes = False
                            self.update_title()
                            self.status_var.set("Original formatting restored from file")
                        else:
                            messagebox.showerror("Error", "Failed to reload file")
                else:
                    messagebox.showinfo("Restore Original", 
                        "No file loaded and no backup available.")
        except Exception as e:
            self.status_var.set(f"Error restoring original formatting: {e}")

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
        """Convert text editor content to relative time format"""
        self._operation_description = "Convert to relative time"
        try:
            # Parse current text content
            text_content = self.text_editor.get(1.0, tk.END).strip()
            if not text_content:
                self.status_var.set("No text to convert")
                return
            
            # Load into temporary PWL data
            temp_pwl_data = PwlData()
            if temp_pwl_data.load_from_text(text_content):
                # Convert to relative time format
                relative_text = temp_pwl_data.to_text_precise(use_relative_time=True, precision=9)
                
                # Update text editor
                self.text_editor.delete(1.0, tk.END)
                self.text_editor.insert(1.0, relative_text)
                
                # Update main data and views
                self.pwl_data = temp_pwl_data
                self.update_table()
                self.update_plot()
                self.mark_unsaved()
                
                self.status_var.set("Converted to relative time format")
            else:
                messagebox.showerror("Conversion Error", "Invalid PWL text format. Cannot convert.")
                
        except Exception as e:
            messagebox.showerror("Conversion Error", f"Failed to convert to relative time: {e}")

    def convert_to_absolute(self):
        """Convert text editor content to absolute time format"""
        self._operation_description = "Convert to absolute time"
        try:
            # Parse current text content
            text_content = self.text_editor.get(1.0, tk.END).strip()
            if not text_content:
                self.status_var.set("No text to convert")
                return
            
            # Load into temporary PWL data
            temp_pwl_data = PwlData()
            if temp_pwl_data.load_from_text(text_content):
                # Convert to absolute time format
                absolute_text = temp_pwl_data.to_text_precise(use_relative_time=False, precision=9)
                
                # Update text editor
                self.text_editor.delete(1.0, tk.END)
                self.text_editor.insert(1.0, absolute_text)
                
                # Update main data and views
                self.pwl_data = temp_pwl_data
                self.update_table()
                self.update_plot()
                self.mark_unsaved()
                
                self.status_var.set("Converted to absolute time format")
            else:
                messagebox.showerror("Conversion Error", "Invalid PWL text format. Cannot convert.")
                
        except Exception as e:
            messagebox.showerror("Conversion Error", f"Failed to convert to absolute time: {e}")

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
