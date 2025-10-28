"""
Undo history management for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

from pwl_parser import PwlData


class UndoRedoManager:
	def __init__(self, max_history=50):
		self.undo_stack = []      # List of (text_snapshot, description)
		self.redo_stack = []      # List of (text_snapshot, description)
		self.max_history = max_history
		self.initial_state_saved = False  # Track if we've saved the initial state
    
	def save_state(self, pwl_data, description="Edit"):
		"""Save current state as text snapshot"""
		# Always save initial state (even if empty) to establish baseline
		if not self.initial_state_saved and pwl_data.get_point_count() == 0:
			text_snapshot = ""  # Empty state baseline
			self.undo_stack.append((text_snapshot, "Initial empty state"))
			self.initial_state_saved = True
			return
        
		# For non-empty states, proceed normally
		if pwl_data.get_point_count() == 0:
			text_snapshot = ""
		else:
			text_snapshot = pwl_data.to_text_precise(
				use_relative_time=True, 
				precision=9, 
				preserve_original=True
			)
        
		# Avoid duplicate consecutive states
		if (self.undo_stack and 
			self.undo_stack[-1][0] == text_snapshot):
			return
        
		self.undo_stack.append((text_snapshot, description))
        
		# Limit history size (but keep at least one state)
		if len(self.undo_stack) > self.max_history:
			self.undo_stack.pop(0)
        
		# Clear redo stack when new operation is performed
		self.redo_stack.clear()
    
	def undo(self):
		"""Return previous state and description"""
		if not self.can_undo():
			return None, "Nothing to undo"
        
		# Move current state to redo stack
		current_state = self.undo_stack.pop()
		self.redo_stack.append(current_state)
        
		if self.undo_stack:
			# Restore previous state
			text_snapshot, description = self.undo_stack[-1]
			pwl_data = PwlData()
            
			# Handle empty state
			if text_snapshot == "":
				return pwl_data, "Empty state"
            
			# Load from text
			if pwl_data.load_from_text(text_snapshot):
				return pwl_data, description
			else:
				# Fallback: if text parsing fails, return empty state
				return PwlData(), f"Parse failed for: {description}"
        
		# No previous state, return empty (shouldn't happen with proper initialization)
		return PwlData(), "Initial state"
    
	def redo(self):
		"""Return next state and description"""
		if not self.can_redo():
			return None, "Nothing to redo"
        
		text_snapshot, description = self.redo_stack.pop()
		self.undo_stack.append((text_snapshot, description))
        
		pwl_data = PwlData()
        
		# Handle empty state
		if text_snapshot == "":
			return pwl_data, "Empty state"
        
		# Load from text
		if pwl_data.load_from_text(text_snapshot):
			return pwl_data, description
		else:
			# Fallback: if text parsing fails, return empty state
			return PwlData(), f"Parse failed for: {description}"
    
	def can_undo(self):
		return len(self.undo_stack) > 1  # Keep at least current state
    
	def can_redo(self):
		return len(self.redo_stack) > 0
    
	def clear_history(self):
		"""Clear all undo/redo history"""
		self.undo_stack.clear()
		self.redo_stack.clear()
		self.initial_state_saved = False
    
	def get_undo_description(self):
		"""Get description of what would be undone"""
		if len(self.undo_stack) > 1:
			return self.undo_stack[-2][1]  # Previous state description
		return "Initial state"
    
	def get_redo_description(self):
		"""Get description of what would be redone"""
		if self.redo_stack:
			return self.redo_stack[-1][1]
		return "Nothing to redo"
