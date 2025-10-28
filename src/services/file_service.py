"""
File dialog helpers for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from __future__ import annotations

import os
import sys
from tkinter import filedialog
from typing import Optional, Tuple


class FileService:
    def __init__(self):
        self.last_directory: Optional[str] = None

    def get_examples_dir(self) -> str:
        if getattr(sys, 'frozen', False):
            script_dir = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # __file__ is in services/, go up to src/, then up one to project root
            script_dir = os.path.dirname(os.path.dirname(script_dir))
        examples_dir = os.path.join(script_dir, 'examples')
        return examples_dir if os.path.exists(examples_dir) else script_dir

    def get_initial_dir(self) -> str:
        return self.last_directory if self.last_directory else self.get_examples_dir()

    def ask_open(self, initial_dir: Optional[str] = None, filetypes: Optional[Tuple[Tuple[str, str], ...]] = None) -> Optional[str]:
        path = filedialog.askopenfilename(
            title="Open PWL File",
            initialdir=initial_dir or self.get_initial_dir(),
            filetypes=filetypes or (("PWL/Text Files", "*.pwl;*.txt"), ("PWL Files", "*.pwl"), ("Text Files", "*.txt"), ("All Files", "*.*")),
        )
        if path:
            self.last_directory = os.path.dirname(path)
            return path
        return None

    def ask_save_as(self, initial_dir: Optional[str] = None, defaultextension: str = ".pwl",
                     filetypes: Optional[Tuple[Tuple[str, str], ...]] = None) -> Optional[str]:
        path = filedialog.asksaveasfilename(
            title="Save PWL File",
            initialdir=initial_dir or self.get_initial_dir(),
            defaultextension=defaultextension,
            filetypes=filetypes or (("PWL/Text Files", "*.pwl;*.txt"), ("PWL Files", "*.pwl"), ("Text Files", "*.txt"), ("All Files", "*.*")),
        )
        if path:
            self.last_directory = os.path.dirname(path)
            return path
        return None
