"""
PWL Editor GUI Geometry - Layout and Widget Creation
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic) - Code development and architecture
License: GPL-3.0-or-later
"""

import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class PWLEditorGeometry:
    def __init__(self, root, callback_handler=None):
        self.root = root
        self.callback_handler = callback_handler
        
        self.root.title("PWL Editor - Piecewise Linear Waveform Editor")
        self.root.geometry("1200x600")
        
        self.widgets = {}
        
        self.create_menu()
        self.create_main_layout()
        self.create_table_view()
        self.create_text_view()
        self.create_plot_view()
        
        if self.callback_handler and hasattr(self.callback_handler, 'on_closing'):
            self.root.protocol("WM_DELETE_WINDOW", self.callback_handler.on_closing)

    def create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self._callback('new_file'), accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self._callback('open_file'), accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._callback('save_file'), accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self._callback('save_file_as'), accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._callback('on_closing'))
        
        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Sort by Time", command=self._callback('sort_data'))
        edit_menu.add_command(label="Remove Selected", command=self._callback('remove_selected'))
        edit_menu.add_separator()
        edit_menu.add_command(label="Clear All", command=self._callback('clear_all'))
        
        # Format menu
        format_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Format", menu=format_menu)
        format_menu.add_command(label="Convert Time to SI Prefix", command=self._callback('convert_time_to_si'))
        format_menu.add_command(label="Convert Time to Scientific", command=self._callback('convert_time_to_scientific'))
        format_menu.add_command(label="Convert Value to SI Prefix", command=self._callback('convert_value_to_si'))
        format_menu.add_command(label="Convert Value to Scientific", command=self._callback('convert_value_to_scientific'))
        format_menu.add_separator()
        format_menu.add_command(label="Convert All to SI Prefix", command=self._callback('convert_all_to_si'))
        format_menu.add_command(label="Convert All to Scientific", command=self._callback('convert_all_to_scientific'))
        format_menu.add_separator()
        format_menu.add_command(label="Restore Original Formatting", command=self._callback('restore_original_formatting'))
        
        # Keyboard shortcuts
        self.root.bind('<Control-n>', lambda e: self._callback('new_file')())
        self.root.bind('<Control-o>', lambda e: self._callback('open_file')())
        self.root.bind('<Control-s>', lambda e: self._callback('save_file')())
        self.root.bind('<Control-S>', lambda e: self._callback('save_file_as')())
        
        # Undo/Redo shortcuts
        self.root.bind('<Control-z>', lambda e: self._callback('undo')())
        self.root.bind('<Control-y>', lambda e: self._callback('redo')())
        self.root.bind('<Control-Z>', lambda e: self._callback('redo')())  # Ctrl+Shift+Z
    
    def _callback(self, method_name):
        def wrapper(*args, **kwargs):
            if self.callback_handler and hasattr(self.callback_handler, method_name):
                return getattr(self.callback_handler, method_name)(*args, **kwargs)
        return wrapper
    
    def create_main_layout(self):
        self.status_var = tk.StringVar(value="Ready")
        self.parse_status_var = tk.StringVar(value="")
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        status_main = ttk.Label(status_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_main.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 1), pady=1)
        
        status_parse = ttk.Label(status_frame, textvariable=self.parse_status_var, relief=tk.SUNKEN, width=30)
        status_parse.pack(side=tk.RIGHT, padx=(1, 2), pady=1)
        
        self.widgets['status_var'] = self.status_var
        self.widgets['parse_status_var'] = self.parse_status_var
        
        # Main content area with horizontal split
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel with tabs (Table/Text)
        self.left_frame = ttk.Frame(main_paned)
        main_paned.add(self.left_frame, weight=1)
        
        # Right panel for plot
        self.right_frame = ttk.Frame(main_paned)
        main_paned.add(self.right_frame, weight=1)
        
        # Create notebook for tabbed interface
        self.notebook = ttk.Notebook(self.left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Store widget references
        self.widgets['notebook'] = self.notebook
        
        # Bind tab change event
        self.notebook.bind('<<NotebookTabChanged>>', self._callback('on_tab_changed'))

    def create_table_view(self):
        """Create table view for editing data points"""
        # Table tab
        self.table_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.table_frame, text="Table")
        
        # Control buttons frame
        control_frame = ttk.LabelFrame(self.table_frame, text="Table Controls")
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Add Above", command=self._callback('add_point_above')).grid(row=0, column=0, padx=5, pady=2)
        ttk.Button(control_frame, text="Add Below", command=self._callback('add_point_below')).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(control_frame, text="Move Up", command=self._callback('move_point_up')).grid(row=0, column=2, padx=5, pady=2)
        ttk.Button(control_frame, text="Move Down", command=self._callback('move_point_down')).grid(row=0, column=3, padx=5, pady=2)
        ttk.Button(control_frame, text="Remove", command=self._callback('remove_selected')).grid(row=0, column=4, padx=5, pady=2)
        
        # Table frame with scrollbars
        table_container = ttk.Frame(self.table_frame)
        table_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create treeview for table
        columns = ('Index', 'Time', 'Value', 'Type')
        self.table = ttk.Treeview(table_container, columns=columns, show='headings', height=15)
        
        # Configure columns
        self.table.heading('Index', text='#')
        self.table.heading('Time', text='Time (s)')
        self.table.heading('Value', text='Value')
        self.table.heading('Type', text='Type')
        
        self.table.column('Index', width=50, anchor=tk.CENTER)
        self.table.column('Time', width=120, anchor=tk.E)
        self.table.column('Value', width=120, anchor=tk.E)
        self.table.column('Type', width=80, anchor=tk.CENTER)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.table.yview)
        h_scrollbar = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack table and scrollbars
        self.table.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)
        
        # Store widget references
        self.widgets['table'] = self.table
        
        # Bind events
        self.table.bind('<Double-1>', self._callback('start_inline_edit'))
        self.table.bind('<Return>', self._callback('start_inline_edit'))
        self.table.bind('<Delete>', self._callback('remove_selected'))
        self.table.bind('<<TreeviewSelect>>', self._callback('on_table_select'))

    def create_text_view(self):
        """Create text editor view for direct PWL editing"""
        # Text tab
        self.text_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.text_frame, text="Text")
        
        # Conversion buttons frame
        convert_frame = ttk.Frame(self.text_frame)
        convert_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(convert_frame, text="Convert Time Format:").pack(side=tk.LEFT, padx=5)
        ttk.Button(convert_frame, text="To Relative Time", command=self._callback('convert_to_relative')).pack(side=tk.LEFT, padx=5)
        ttk.Button(convert_frame, text="To Absolute Time", command=self._callback('convert_to_absolute')).pack(side=tk.LEFT, padx=5)
        
        # Export format dropdown
        ttk.Label(convert_frame, text="Export Format:").pack(side=tk.LEFT, padx=(20, 5))
        self.export_format_var = tk.StringVar(value="preserve_mixed")
        export_formats = [
            ("Preserve Mixed", "preserve_mixed"),
            ("Force Relative", "force_relative"), 
            ("Force Absolute", "force_absolute")
        ]
        self.export_format_combo = ttk.Combobox(convert_frame, textvariable=self.export_format_var, 
                                               values=[fmt[0] for fmt in export_formats], 
                                               state="readonly", width=15)
        self.export_format_combo.pack(side=tk.LEFT, padx=5)
        
        # Update text when format changes
        self.export_format_combo.bind('<<ComboboxSelected>>', self._callback('on_export_format_changed'))
        
        # Text editor with scrollbars
        text_container = ttk.Frame(self.text_frame)
        text_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.text_editor = tk.Text(text_container, wrap=tk.NONE, font=('Consolas', 10))
        
        # Scrollbars for text editor
        text_v_scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=self.text_editor.yview)
        text_h_scrollbar = ttk.Scrollbar(text_container, orient=tk.HORIZONTAL, command=self.text_editor.xview)
        self.text_editor.configure(yscrollcommand=text_v_scrollbar.set, xscrollcommand=text_h_scrollbar.set)
        
        # Pack text editor and scrollbars
        self.text_editor.grid(row=0, column=0, sticky='nsew')
        text_v_scrollbar.grid(row=0, column=1, sticky='ns')
        text_h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        text_container.grid_rowconfigure(0, weight=1)
        text_container.grid_columnconfigure(0, weight=1)
        
        # Store widget references
        self.widgets['text_editor'] = self.text_editor
        self.widgets['export_format_var'] = self.export_format_var
        
        # Bind text change event
        self.text_editor.bind('<KeyRelease>', self._callback('on_text_changed'))

    def create_plot_view(self):
        """Create matplotlib plot for waveform preview"""
        # Plot frame
        plot_frame = ttk.LabelFrame(self.right_frame, text="Waveform Preview")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create matplotlib figure
        self.figure, self.ax = plt.subplots(figsize=(6, 4))
        self.figure.patch.set_facecolor('white')
        
        # Embed plot in tkinter
        self.canvas = FigureCanvasTkAgg(self.figure, plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Configure plot
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Value')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_title('PWL Waveform')
        
        # Store widget references
        self.widgets['figure'] = self.figure
        self.widgets['ax'] = self.ax
        self.widgets['canvas'] = self.canvas
    
    def get_widget(self, name):
        """Get widget reference by name"""
        return self.widgets.get(name)
    
    def get_all_widgets(self):
        """Get all widget references"""
        return self.widgets.copy()


