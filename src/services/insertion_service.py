"""
Smart insertion utilities for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""
from __future__ import annotations

import re
from typing import Optional, List

from pwl_parser import PwlPoint
from . import formatting as fmt


class SmartInsertion:
	"""
	Handles intelligent point insertion for PWL data with:
	- Notation preservation (SI prefix, scientific, decimal)
	- Consistent stepping patterns
	- Sensible defaults for empty lists
	- Gap-aware calculations
	"""
    
	# Default settings
	DEFAULT_EMPTY_LIST_UNIT = 'u'  # microseconds
	DEFAULT_EMPTY_LIST_STEP = 1    # 1 microsecond steps
    
	def __init__(self):
		"""Initialize the smart insertion handler"""
		# reference SI map now comes from shared formatting utils
		self.si_prefixes = {k: v for k, v in fmt.SI_PREFIXES.items() if k in ['p','n','u','m','k','M','G']}
    
	def calculate_time_below(self, current_point: PwlPoint, next_point: Optional[PwlPoint] = None) -> str:
		"""
		Calculate intelligent time for point insertion below current point.
		Enhanced for maximum user-friendliness.
		"""
		current_time_str = current_point.time_str
		current_time_val = current_point.get_time_value()
        
		# Handle None values gracefully
		if current_time_val is None:
			current_time_val = 0.0
        
		# Determine consistent step size based on notation and context
		step_size = self._determine_consistent_step_size(current_time_str, current_time_val)
        
		# Consider gap to next point if it exists
		if next_point:
			next_time_val = next_point.get_time_value()
			if next_time_val is not None:
				gap = next_time_val - current_time_val
                
				# If our step would exceed the gap, use a fraction of the gap
				if step_size >= gap * 0.9:  # Leave some margin
					step_size = gap * 0.5
        
		new_time_val = current_time_val + step_size

		# Try insertion-local rounding if we have a next bound to stay strictly between
		if next_point is not None:
			nxt_val = next_point.get_time_value()
			if nxt_val is not None:
				rounded = self._maybe_round_insert(
					new_time_val,
					lower_bound=min(current_time_val, nxt_val),
					upper_bound=max(current_time_val, nxt_val),
					reference_str=current_time_str,
				)
				if rounded is not None:
					return rounded

		# Format with optimization for user-friendliness
		result = self._format_time_like_reference(new_time_val, current_time_str)

		# If the result is awkward, try to optimize it
		if fmt.is_awkward_format(result):
			optimized = fmt.suggest_optimal(new_time_val)
			return optimized

		return result
    
	def calculate_time_above(self, current_point: PwlPoint, prev_point: Optional[PwlPoint] = None) -> str:
		"""
		Calculate intelligent time for point insertion above current point.
		Enhanced for maximum user-friendliness including small gap handling.
		"""
		current_time_str = current_point.time_str
		current_time_val = current_point.get_time_value()
        
		# Handle None values gracefully
		if current_time_val is None:
			current_time_val = 0.0
        
		if prev_point:
			# Calculate intermediate time between previous and current
			prev_time_val = prev_point.get_time_value()
			if prev_time_val is None:
				prev_time_val = 0.0
                
			gap = current_time_val - prev_time_val
            
			# Smart gap handling
			if gap <= 0:
				# No gap or negative gap - use small step before current
				step_size = self._determine_consistent_step_size(current_time_str, current_time_val)
				new_time_val = max(0, current_time_val - step_size * 0.1)  # Small step back
				return self._format_time_like_reference(new_time_val, current_time_str)
            
			# Determine what a "normal" step would be for each point
			prev_step = self._determine_consistent_step_size(prev_point.time_str, prev_time_val)
			curr_step = self._determine_consistent_step_size(current_time_str, current_time_val)
			typical_step = min(prev_step, curr_step)  # Use smaller typical step
            
			if gap < typical_step * 0.5:
				# Gap is smaller than half a typical step - use precise intermediate
				new_time_val = prev_time_val + (gap * 0.5)

				# Insertion-local rounding first: try to snap to simple rounded value within bounds
				snapped = self._maybe_round_insert(
					new_time_val,
					lower_bound=prev_time_val,
					upper_bound=current_time_val,
					reference_str=current_time_str,
				)
				if snapped is not None:
					return snapped

				# Choose the format that makes the result most readable
				prev_formatted = self._format_time_like_reference(new_time_val, prev_point.time_str)
				curr_formatted = self._format_time_like_reference(new_time_val, current_time_str)
				optimal_formatted = fmt.suggest_optimal(new_time_val)

				# Pick the most readable option
				options = [
					(prev_formatted, len(prev_formatted), not self._is_awkward_format(prev_formatted)),
					(curr_formatted, len(curr_formatted), not self._is_awkward_format(curr_formatted)),
					(optimal_formatted, len(optimal_formatted), True)  # Optimal is always good
				]
				# Sort by: not awkward first, then by length
				return min(options, key=lambda x: (not x[2], x[1]))[0]
			else:
				# Normal gap - use geometric mean with smart formatting
				new_time_val = prev_time_val + (gap * 0.5)
                
				# Try insertion-local rounding first (prioritize clean suggestions)
				snapped = self._maybe_round_insert(
					new_time_val,
					lower_bound=prev_time_val,
					upper_bound=current_time_val,
					reference_str=current_time_str,
				)
				if snapped is not None:
					return snapped
                
				# Special handling for very wide gaps (e.g., microseconds to seconds)
				# If the gap spans more than 3 orders of magnitude, suggest a sensible intermediate
				gap_ratio = max(current_time_val, prev_time_val) / min(current_time_val, prev_time_val)
				if gap_ratio > 1000:  # More than 3 orders of magnitude difference
					# Use the optimal format for the midpoint instead of trying to match either endpoint
					return fmt.suggest_optimal(new_time_val)

				# Choose format based on which point the result is closer to, but optimize for readability
				time_diff_to_current = abs(new_time_val - current_time_val)
				time_diff_to_prev = abs(new_time_val - prev_time_val)

				if time_diff_to_current <= time_diff_to_prev:
					# Closer to current point - but check if format is user-friendly
					candidate = self._format_time_like_reference(new_time_val, current_time_str)
					# If it creates an awkward format, try optimal format instead
					if fmt.is_awkward_format(candidate):
						return fmt.suggest_optimal(new_time_val)
					return candidate
				else:
					# Closer to previous point
					candidate = self._format_time_like_reference(new_time_val, prev_point.time_str)
					if fmt.is_awkward_format(candidate):
						return fmt.suggest_optimal(new_time_val)
                    
					# Additional check: if the candidate contains many decimal places, try optimal
					if "." in candidate and len(candidate.split(".")[1].rstrip('0')) > 4:
						return fmt.suggest_optimal(new_time_val)
                    
					return candidate
		else:
			# No previous point - insert before current with consistent step back
			step_size = self._determine_consistent_step_size(current_time_str, current_time_val)
			new_time_val = max(0, current_time_val - step_size)
			return self._format_time_like_reference(new_time_val, current_time_str)
    
	def get_empty_list_defaults(self) -> tuple[str, str]:
		"""
		Get sensible defaults for starting an empty PWL list.
        
		Returns:
			Tuple of (time_str, value_str) for the first point
		"""
		return ("0", "0")
    
	def get_empty_list_next(self, last_point: PwlPoint) -> str:
		"""
		Get next time for building up from an initially empty list.
        
		Args:
			last_point: The last point that was added
            
		Returns:
			Formatted time string for the next point
		"""
		last_time_str = last_point.time_str
        
		# If the last point is still "0", start with default unit
		if last_time_str.strip() == "0":
			return f"{self.DEFAULT_EMPTY_LIST_STEP}{self.DEFAULT_EMPTY_LIST_UNIT}"
        
		# Otherwise use consistent stepping
		return self.calculate_time_below(last_point)
    
	def _determine_consistent_step_size(self, time_str: str, time_val: float) -> float:
		"""
		Determine consistent step size that maintains predictable progression.
        
		This fixes the exponential growth issue by using fixed steps within
		the same magnitude range.
		"""
		# Check for SI prefix notation
		si_match = re.search(r'(\d+(?:\.\d+)?)\s*([numkMG])(?:s)?$', time_str.strip())
		if si_match:
			magnitude_str, prefix = si_match.groups()
			magnitude = float(magnitude_str)
			prefix_value = self.si_prefixes.get(prefix, 1)
            
			# Use consistent stepping within the same prefix
			if magnitude < 10:
				# Small numbers: step by 1 unit (1n → 2n → 3n)
				step_magnitude = 1
			elif magnitude < 100:
				# Medium numbers: step by 10 units (20n → 30n → 40n)  
				step_magnitude = 10
			else:
				# Large numbers: step by 50 or 100 units
				step_magnitude = 50 if magnitude < 500 else 100
            
			return step_magnitude * prefix_value
        
		# Check for scientific notation
		sci_match = re.search(r'(\d+(?:\.\d+)?)\s*e\s*([+-]?\d+)', time_str.strip())
		if sci_match:
			mantissa_str, exp_str = sci_match.groups()
			mantissa = float(mantissa_str)
			exp = int(exp_str)
            
			# Use consistent stepping within same scientific magnitude
			if mantissa < 2:
				step_mantissa = 1  # 1e-3 → 2e-3 → 3e-3
			elif mantissa < 10:
				step_mantissa = 1  # 5e-3 → 6e-3 → 7e-3
			else:
				step_mantissa = 10  # 10e-3 → 20e-3 → 30e-3
            
			return step_mantissa * (10 ** exp)
        
		# For plain numbers, use sensible stepping
		if time_val == 0:
			# Default for zero: 1 microsecond
			return self.DEFAULT_EMPTY_LIST_STEP * self.si_prefixes[self.DEFAULT_EMPTY_LIST_UNIT]
		elif time_val < 1e-6:
			# Sub-microsecond: step in nanoseconds
			return 1e-9
		elif time_val < 1e-3:
			# Microsecond range: step in microseconds
			return 1e-6
		elif time_val < 1:
			# Millisecond range: step in milliseconds
			return 1e-3
		else:
			# Second range: step in 0.1 seconds
			return 0.1
    
	def _format_time_like_reference(self, time_val: float, reference_str: str) -> str:
		"""Format time value in the same style as reference string"""
		# Check if reference uses SI prefix
		si_match = re.search(r'(\d+(?:\.\d+)?)\s*([numkMG])(?:s)?$', reference_str.strip())
		if si_match:
			_, prefix = si_match.groups()
			if prefix in self.si_prefixes:
				# Convert to same prefix
				converted_val = time_val / self.si_prefixes[prefix]
				if abs(converted_val - round(converted_val)) < 1e-10:
					return f"{int(round(converted_val))}{prefix}"
				else:
					return f"{converted_val:g}{prefix}"
        
		# Check if reference uses scientific notation
		sci_match = re.search(r'(\d+(?:\.\d+)?)\s*e\s*([+-]?\d+)', reference_str.strip())
		if sci_match:
			# Use stepped scientific notation for consistency
			return fmt.format_engineering(time_val)
        
		# Handle edge cases like "0"
		if reference_str.strip() == "0" and time_val > 0:
			# For zero reference, pick the most appropriate format
			return fmt.suggest_optimal(time_val)
        
		# Smart optimization: if the result would be awkwardly large, suggest better format
		if reference_str.strip() and time_val > 0:
			# Check if using reference format would create awkward result
			temp_result = self._try_format_like_reference(time_val, reference_str)
			if temp_result and fmt.is_awkward_format(temp_result):
				return fmt.suggest_better_si(time_val)
        
		# Default to smart formatting
		return f"{time_val:g}"
    
	def _try_format_like_reference(self, time_val: float, reference_str: str) -> str:
		"""Try formatting like reference without optimization, for testing awkwardness"""
		import re
		# Check if reference uses SI prefix
		si_match = re.search(r'(\d+(?:\.\d+)?)\s*([numkMG])(?:s)?$', reference_str.strip())
		if si_match:
			_, prefix = si_match.groups()
			if prefix in self.si_prefixes:
				converted_val = time_val / self.si_prefixes[prefix]
				if abs(converted_val - round(converted_val)) < 1e-10:
					return f"{int(round(converted_val))}{prefix}"
				else:
					return f"{converted_val:g}{prefix}"
        
		return f"{time_val:g}"
    
	def _suggest_better_si_format(self, time_val: float) -> str:
		"""Suggest the most user-friendly SI format for a time value (wrapper to shared util)."""
		# Prefer shared util for consistency
		return fmt.suggest_better_si(time_val)
    
	def _suggest_optimal_format(self, time_val: float) -> str:
		"""Suggest the most user-friendly format for any time value (wrapper to shared util)."""
		return fmt.suggest_optimal(time_val)
    
	def _is_awkward_format(self, formatted_str: str) -> bool:
		"""Check if a formatted string is awkward/unreadable for users (wrapper)."""
		import re
		return fmt.is_awkward_format(formatted_str)
    
	def _format_scientific(self, value: float) -> str:
		"""Backwards-compatible wrapper; delegates to shared formatting."""
		return fmt.format_engineering(value)

	def _maybe_round_insert(
		self,
		new_time_val: float,
		lower_bound: float,
		upper_bound: float,
		reference_str: str,
	) -> Optional[str]:
		"""
		Try to snap the computed insertion time to a simple rounded value.
		Since insertion is just a suggestion, prioritize clean readable values
		as long as they stay strictly between bounds.

		Rounding strategy (aggressive for user-friendliness):
		- Try clean round numbers in appropriate SI units
		- Try nice decimal values (50, 25, 10, 5, 1, 0.5, 0.1, etc.)
		- Accept any candidate that stays strictly between bounds
		"""
		lo = min(lower_bound, upper_bound)
		hi = max(lower_bound, upper_bound)
        
		# Try clean round numbers in various SI units
		clean_candidates = []
        
		# Generate clean values around the target
		magnitude = new_time_val
		if magnitude > 0:
			# Get the order of magnitude
			import math
			log_mag = math.log10(magnitude)
            
			# Try nice round numbers in nearby magnitudes
			for exp_offset in [-1, 0, 1]:
				target_exp = math.floor(log_mag) + exp_offset
				base_val = 10 ** target_exp
                
				# Try nice multipliers: 1, 2, 5, 10, 20, 25, 50, 100
				for mult in [1, 2, 5, 10, 20, 25, 50, 100]:
					candidate_val = mult * base_val
					if lo < candidate_val < hi:
						clean_candidates.append(candidate_val)
                
				# Also try fractional multipliers for finer control
				for mult in [0.1, 0.2, 0.5]:
					candidate_val = mult * base_val
					if lo < candidate_val < hi:
						clean_candidates.append(candidate_val)
        
		# Sort candidates by how close they are to the original value
		if clean_candidates:
			clean_candidates.sort(key=lambda x: abs(x - new_time_val))
            
			# Return the closest clean candidate in optimal format
			# But make sure it's not too close to the bounds
			for candidate_val in clean_candidates:
				# Ensure some minimum distance from bounds to avoid equality
				min_gap = min(abs(candidate_val - lo), abs(candidate_val - hi))
				total_gap = hi - lo
                
				# Require at least 1% of the total gap as buffer from bounds
				if min_gap > total_gap * 0.01:
					return fmt.suggest_optimal(candidate_val)
        
		# Fallback: try the original SI prefix-based rounding
		ref = reference_str.strip()
		si_match = re.search(r'(?:\d+(?:\.\d+)?)\s*([fpnumkMG])(?:s)?$', ref)
		if si_match:
			prefix = si_match.group(1)
			mult = fmt.SI_PREFIXES.get(prefix)
			if mult:
				converted = new_time_val / mult
				candidates = []
				# Try various rounding levels
				candidates.append(round(converted))  # Nearest integer
				candidates.append(round(converted * 2) / 2)  # Nearest 0.5
				candidates.append(round(converted * 10) / 10)  # Nearest 0.1
                
				for cand in candidates:
					if abs(cand - converted) < 1e-12:
						continue
					cand_val = cand * mult
					if lo < cand_val < hi:
						return self._format_time_like_reference(cand_val, reference_str)

		return None
    
	def analyze_sequence_pattern(self, points: List[PwlPoint]) -> dict:
		"""
		Analyze a sequence of points to understand the stepping pattern.
        
		Returns:
			Dictionary with pattern analysis for debugging/optimization
		"""
		if len(points) < 2:
			return {"pattern": "insufficient_data", "suggestion": "use_defaults"}
        
		# Analyze time differences
		diffs = []
		notations = []
        
		for i in range(1, len(points)):
			prev_time = points[i-1].get_time_value()
			curr_time = points[i].get_time_value()
            
			# Handle None values
			if prev_time is None:
				prev_time = 0.0
			if curr_time is None:
				curr_time = 0.0
                
			diffs.append(curr_time - prev_time)
			notations.append(points[i].time_str)
        
		# Detect if differences are consistent
		variance = 0.0
		if len(diffs) > 1:
			avg_diff = sum(diffs) / len(diffs)
			variance = sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)
			is_consistent = variance < (avg_diff * 0.1) ** 2  # 10% tolerance
		else:
			is_consistent = True
			avg_diff = diffs[0] if diffs else 0
        
		return {
			"pattern": "consistent" if is_consistent else "variable",
			"average_step": avg_diff,
			"step_variance": variance,
			"predominant_notation": max(set(notations), key=notations.count) if notations else "unknown",
			"suggestion": "maintain_pattern" if is_consistent else "use_adaptive_stepping"
		}
