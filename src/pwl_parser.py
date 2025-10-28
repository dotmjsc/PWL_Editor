"""
PWL Parser - LTSpice-style PWL text parser and data model
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

import logging
import numpy as np
import mimetypes
from si_prefix import si_parse
import os

def ltspice_si_parse(value_str):
    """
    Parse SI values with LTSpice compatibility
    Handles LTSpice's 'u' notation for microseconds
    """
    # Remove leading '+' for relative time values
    clean_str = value_str.lstrip('+')
    
    # Convert LTSpice 'u' notation to proper microsecond notation
    # LTSpice uses 'u' for microseconds, but si_prefix expects 'µ' or doesn't recognize 'u'
    if clean_str.endswith('u'):
        # Convert 'u' to 'e-6' (scientific notation)
        numeric_part = clean_str[:-1]
        try:
            # Parse the numeric part and convert to microseconds
            numeric_value = float(numeric_part)
            return numeric_value * 1e-6
        except ValueError:
            # If numeric parsing fails, fall back to original si_parse
            pass
    
    # For all other cases, use standard si_prefix parsing
    return si_parse(clean_str)


class PwlPoint:
    """Represents a single PWL point with both string and computed values"""
    def __init__(self, time_str, value_str, is_relative=False):
        self.time_str = time_str.strip()     # Time as string (e.g., "5n", "1.2e-6", "10u")
        self.value_str = value_str.strip()   # Value as string (e.g., "3.3", "0", "1e-3")
        self.is_relative = is_relative       # True if this is a +delta point
        
        # Computed values (cached for performance)
        self._time_value = None
        self._value_value = None
        self._compute_values()
    
    def _compute_values(self):
        """Compute numeric values from strings"""
        try:
            # Remove '+' prefix for relative times
            clean_time = self.time_str.lstrip('+')
            self._time_value = ltspice_si_parse(clean_time)
        except:
            self._time_value = 0.0
            
        try:
            self._value_value = ltspice_si_parse(self.value_str)
        except:
            self._value_value = 0.0
    
    def get_time_value(self):
        """Get computed time value"""
        return self._time_value
    
    def get_value_value(self):
        """Get computed value"""
        return self._value_value
    
    # For backward compatibility, add properties
    @property
    def time_value(self):
        """Backward compatibility for time_value"""
        return self._time_value
    
    @property
    def value(self):
        """Backward compatibility for value"""
        return self._value_value
    
    def update_time_str(self, new_time_str):
        """Update time string and recompute values"""
        self.time_str = new_time_str.strip()
        self._compute_values()
    
    def update_value_str(self, new_value_str):
        """Update value string and recompute values"""
        self.value_str = new_value_str.strip()
        self._compute_values()
    
    def get_absolute_time(self, previous_absolute_time=0.0):
        """Get the absolute time for this point"""
        if self.is_relative:
            return previous_absolute_time + (self._time_value or 0.0)
        else:
            return self._time_value or 0.0
    
    def to_text(self):
        """Convert point to text representation"""
        if self.is_relative and not self.time_str.startswith('+'):
            return f"+{self.time_str} {self.value_str}"
        else:
            return f"{self.time_str} {self.value_str}"
    
    def _format_number(self, number, precision):
        """Format number with given precision"""
        if abs(number) > 10**(precision) or (number != 0 and abs(number) < 10**(-precision+1)):
            return f"{number:.{precision-1}e}"
        else:
            formatted = f"{number:.{precision}g}"
            return formatted


class PwlData:
    def __init__(self):
        self.points = []                  # List of PwlPoint objects
        self._values_discrete = []
        self._timestamps_discrete = []
        self._discrete_dirty = True
        self.timestep = 0.001             # Default timestep for discretization
        self.default_format = 'relative'  # 'relative', 'absolute', 'mixed'
    
    # Backward compatibility properties
    @property
    def values(self):
        """Get values list for backward compatibility"""
        return [point.get_value_value() for point in self.points]
    
    @property
    def timestamps(self):
        """Get absolute timestamps list for backward compatibility"""
        absolute_times = []
        current_time = 0.0
        for point in self.points:
            current_time = point.get_absolute_time(current_time)
            absolute_times.append(current_time)
        return absolute_times
    
    def clear(self):
        """Clear all data points"""
        self.points.clear()
        self._update_discrete()
    
    def add_point(self, time_str, value_str, is_relative=None):
        """Add a single point and maintain time ordering"""
        # Coerce numeric inputs to string form for downstream formatting logic
        if isinstance(time_str, (int, float)):
            time_str = f"{time_str:g}"
        if isinstance(value_str, (int, float)):
            value_str = f"{value_str:g}"

        # Auto-detect format if not specified
        if is_relative is None:
            is_relative = len(self.points) > 0 and self.default_format == 'relative'
        
        # Convert time string to value for ordering logic
        try:
            time_val = ltspice_si_parse(time_str.lstrip('+'))
        except:
            time_val = 0.0
            
        # Convert relative time to absolute for insertion logic
        if is_relative and len(self.points) > 0:
            last_abs_time = self.get_absolute_time(len(self.points) - 1)
            abs_time = last_abs_time + time_val
        else:
            abs_time = time_val
            is_relative = False  # First point is always absolute
        
        # Create new point with original strings
        new_point = PwlPoint(time_str, value_str, is_relative)
        
        # Insert in correct position to maintain time ordering
        insert_pos = 0
        for i, existing_point in enumerate(self.points):
            existing_abs_time = self.get_absolute_time(i)
            if abs_time > existing_abs_time:
                insert_pos = i + 1
            else:
                break

        self.points.insert(insert_pos, new_point)
        self._update_relative_times_after_insert(insert_pos)
        self._update_discrete()
    
    def remove_point(self, index):
        """Remove point at given index"""
        if 0 <= index < len(self.points):
            self.points.pop(index)
            self._update_relative_times_after_remove(index)
            self._update_discrete()
    
    def update_point(self, index, time, value, is_relative=None):
        """Update point at given index"""
        if 0 <= index < len(self.points):
            old_point = self.points[index]
            if is_relative is None:
                is_relative = old_point.is_relative
            
            # Remove old point and add new one
            self.remove_point(index)
            self.add_point(time, value, is_relative)
    
    def get_point(self, index):
        """Get point at given index as (time, value) tuple (absolute time)"""
        if 0 <= index < len(self.points):
            abs_time = self.get_absolute_time(index)
            return (abs_time, self.points[index].value)
        return None
    
    def get_point_detailed(self, index):
        """Get detailed point info including format"""
        if 0 <= index < len(self.points):
            point = self.points[index]
            abs_time = self.get_absolute_time(index)
            return {
                'index': index,
                'time_value': point.time_value,
                'absolute_time': abs_time,
                'value': point.value,
                'is_relative': point.is_relative
            }
        return None
    
    def get_absolute_time(self, index):
        """Get absolute time for point at index"""
        if index < 0 or index >= len(self.points):
            return 0.0
        
        current_time = 0.0
        for i in range(index + 1):
            current_time = self.points[i].get_absolute_time(current_time)
        return current_time
    
    def get_point_count(self):
        """Get total number of points"""
        return len(self.points)
    
    def swap_points(self, index1, index2):
        """Swap two points by their indices"""
        if (0 <= index1 < len(self.points) and 
            0 <= index2 < len(self.points) and 
            index1 != index2):
            self.points[index1], self.points[index2] = self.points[index2], self.points[index1]
            return True
        return False
    
    def _update_relative_times_after_insert(self, insert_pos):
        """Update relative times of points after insertion"""
        if insert_pos < len(self.points) - 1:
            # If we inserted a point in the middle, update relative times of following points
            for i in range(insert_pos + 1, len(self.points)):
                if self.points[i].is_relative:
                    # Recalculate relative time based on new predecessor
                    prev_abs_time = self.get_absolute_time(i - 1)
                    curr_abs_time = self.get_absolute_time(i)
                    # This might need adjustment - for now, keep absolute time consistent
                    pass
    
    def _update_relative_times_after_remove(self, removed_index):
        """Update relative times of points after removal"""
        if removed_index < len(self.points):
            # Update relative times of points after the removed one
            for i in range(removed_index, len(self.points)):
                if self.points[i].is_relative and i > 0:
                    # Recalculate relative time based on new predecessor
                    prev_abs_time = self.get_absolute_time(i - 1) 
                    # Keep the same absolute time, adjust the relative delta
                    # This might need more sophisticated logic
                    pass
    
    def _sort_by_time(self):
        """Sort points by absolute time (for backward compatibility)"""
        # Create list of (absolute_time, point) pairs
        time_point_pairs = []
        current_time = 0.0
        for point in self.points:
            current_time = point.get_absolute_time(current_time)
            time_point_pairs.append((current_time, point))
        
        # Sort by absolute time
        time_point_pairs.sort(key=lambda x: x[0])
        
        # Extract sorted points
        self.points = [pair[1] for pair in time_point_pairs]
        
        # Update relative times to maintain consistency
        self._recalculate_relative_times()
    
    def _recalculate_relative_times(self):
        """Recalculate relative times to maintain consistency after sorting"""
        if not self.points:
            return
        
        # First point should be absolute
        self.points[0].is_relative = False
        
        # Recalculate relative deltas for relative points
        for i in range(1, len(self.points)):
            if self.points[i].is_relative:
                prev_abs_time = self.get_absolute_time(i - 1)
                curr_abs_time = self.get_absolute_time(i)
                delta = curr_abs_time - prev_abs_time
                # Update the time string to reflect the new delta
                self.points[i].update_time_str(f"{delta:.9g}")
    
    def _ensure_discrete(self):
        """Compute discrete samples if the cache is marked dirty."""
        if not self._discrete_dirty:
            return

        if len(self.points) > 0:
            timestamps = self.timestamps  # Use property to get absolute times
            values = self.values         # Use property to get values
            try:
                result = discretize(timestamps, values, self.timestep)
            except (MemoryError, ValueError, OverflowError) as exc:
                logging.warning("PWL Parser: Discrete series skipped (%s)", exc)
                self._timestamps_discrete = []
                self._values_discrete = []
            else:
                if result is not None:
                    self._timestamps_discrete, self._values_discrete = result
                else:
                    self._timestamps_discrete = []
                    self._values_discrete = []
        else:
            self._timestamps_discrete = []
            self._values_discrete = []

        self._discrete_dirty = False

    def _update_discrete(self):
        """Mark discrete data dirty; it will be recomputed on demand."""
        self._discrete_dirty = True
        self._timestamps_discrete = []
        self._values_discrete = []

    @property
    def timestamps_discrete(self):
        self._ensure_discrete()
        return self._timestamps_discrete

    @property
    def values_discrete(self):
        self._ensure_discrete()
        return self._values_discrete
    
    def set_timestep(self, timestep):
        """Set timestep for discretization and update"""
        self.timestep = timestep
        self._update_discrete()
    
    def set_default_format(self, format_type):
        """Set default format for new points"""
        if format_type in ['relative', 'absolute', 'mixed']:
            self.default_format = format_type
    
    def convert_to_relative_format(self):
        """Convert all points to relative format (first point absolute)"""
        if not self.points:
            return
        
        # First point becomes absolute
        self.points[0].is_relative = False
        
        # Convert subsequent points to relative
        for i in range(1, len(self.points)):
            prev_abs_time = self.get_absolute_time(i - 1)
            curr_abs_time = self.get_absolute_time(i)
            delta = curr_abs_time - prev_abs_time
            self.points[i].update_time_str(f"{delta:.9g}")
            self.points[i].is_relative = True
        
        self.default_format = 'relative'
    
    def convert_to_absolute_format(self):
        """Convert all points to absolute format"""
        for i, point in enumerate(self.points):
            abs_time = self.get_absolute_time(i)
            point.update_time_str(f"{abs_time:.9g}")
            point.is_relative = False
        
        self.default_format = 'absolute'
    
    def validate(self):
        """Validate PWL data - check if timestamps are properly ordered"""
        if len(self.points) <= 1:
            return True
        
        timestamps = self.timestamps
        for i in range(1, len(timestamps)):
            if timestamps[i] <= timestamps[i-1]:
                return False
        return True
    
    def to_text(self, use_relative_time=True):
        """Export PWL data back to text format (backward compatibility)"""
        return self.to_text_with_format('force_relative' if use_relative_time else 'force_absolute')
    
    def to_text_with_format(self, export_format='auto', precision=6, preserve_original=True):
        """
        Export PWL data with specific format control
        :param export_format: 'auto', 'force_relative', 'force_absolute', 'preserve_mixed'
        :param precision: Number of significant digits
        :param preserve_original: If True, use original text formatting when available
        """
        if len(self.points) == 0:
            return ""
        
        lines = []
        
        if export_format == 'force_relative':
            # Force all to relative format (first absolute)
            for i, point in enumerate(self.points):
                if i == 0:
                    # First point absolute
                    if preserve_original:
                        lines.append(f"{point.time_str} {point.value_str}")
                    else:
                        lines.append(f"{self._format_number(self.get_absolute_time(i), precision, 'auto')} {self._format_number(point.get_value_value(), precision, 'auto')}")
                else:
                    # Subsequent points relative
                    prev_time = self.get_absolute_time(i - 1)
                    curr_time = self.get_absolute_time(i)
                    delta = curr_time - prev_time
                    lines.append(f"+{self._format_number(delta, precision, 'auto')} {self._format_number(point.get_value_value(), precision, 'auto')}")
        
        elif export_format == 'force_absolute':
            # Force all to absolute format
            for i, point in enumerate(self.points):
                abs_time = self.get_absolute_time(i)
                lines.append(f"{self._format_number(abs_time, precision, 'auto')} {self._format_number(point.get_value_value(), precision, 'auto')}")
        
        else:
            # preserve_mixed or auto: preserve original relative/absolute nature
            for point in self.points:
                if preserve_original:
                    lines.append(point.to_text())
                else:
                    if point.is_relative:
                        lines.append(f"+{self._format_number(point.get_time_value(), precision, 'auto')} {self._format_number(point.get_value_value(), precision, 'auto')}")
                    else:
                        lines.append(f"{self._format_number(point.get_time_value(), precision, 'auto')} {self._format_number(point.get_value_value(), precision, 'auto')}")
        
        return "\n".join(lines)
    
    def to_text_precise(self, use_relative_time=True, precision=6, adaptive_precision=False, format_style='auto', preserve_original=False):
        """
        Export PWL data back to text format with precision control
        :param use_relative_time: Use relative time format (+delta) vs absolute
        :param precision: Number of significant digits (3-15)
        :param adaptive_precision: Automatically determine precision needed
        :param format_style: 'auto', 'scientific', 'fixed', 'engineering'
        :param preserve_original: Use original text formatting when available
        :return: PWL formatted text string
        """
        if len(self.timestamps) == 0:
            return ""
        
        lines = []
        
        # If preserve_original and we have points with original strings, use them
        if preserve_original and hasattr(self, 'points') and self.points:
            # Use the to_text_with_format method which already handles preserve_original
            return self.to_text_with_format(
                export_format="preserve_mixed" if use_relative_time else "force_absolute",
                precision=precision,
                preserve_original=True
            )
        
        # Determine precision if adaptive
        if adaptive_precision:
            precision = self._determine_adaptive_precision()
        
        # Clamp precision to reasonable bounds
        precision = max(3, min(15, precision))
        
        if use_relative_time:
            # First point is absolute
            time_str = self._format_number(self.timestamps[0], precision, format_style)
            value_str = self._format_number(self.values[0], precision, format_style)
            lines.append(f"{time_str} {value_str}")
            
            # Subsequent points are relative
            for i in range(1, len(self.timestamps)):
                time_diff = self.timestamps[i] - self.timestamps[i-1]
                time_str = self._format_number(time_diff, precision, format_style)
                value_str = self._format_number(self.values[i], precision, format_style)
                lines.append(f"+{time_str} {value_str}")
        else:
            # All points absolute
            for time, value in zip(self.timestamps, self.values):
                time_str = self._format_number(time, precision, format_style)
                value_str = self._format_number(value, precision, format_style)
                lines.append(f"{time_str} {value_str}")
        
        return "\n".join(lines)
    
    def _format_number(self, number, precision, format_style):
        """Format a number according to specified style and precision"""
        if format_style == 'scientific':
            return f"{number:.{precision-1}e}"
        elif format_style == 'fixed':
            return f"{number:.{precision}f}".rstrip('0').rstrip('.')
        elif format_style == 'engineering':
            # Engineering notation (powers of 3)
            if number == 0:
                return "0"
            import math
            exponent = math.floor(math.log10(abs(number)))
            eng_exp = exponent - (exponent % 3)
            mantissa = number / (10 ** eng_exp)
            if eng_exp == 0:
                return f"{mantissa:.{precision}g}"
            return f"{mantissa:.{precision}g}e{eng_exp:+d}"
        else:  # 'auto' - choose best representation
            # Use scientific for very large or very small numbers
            if abs(number) > 10**(precision) or (number != 0 and abs(number) < 10**(-precision+1)):
                return f"{number:.{precision-1}e}"
            else:
                # Use fixed point, but remove trailing zeros
                formatted = f"{number:.{precision}g}"
                return formatted
    
    def _determine_adaptive_precision(self):
        """Determine the precision needed to preserve all data accurately"""
        if len(self.timestamps) == 0:
            return 6
        
        import math
        
        max_precision = 6  # Start with reasonable default
        
        # Check all values for required precision
        all_numbers = list(self.timestamps) + list(self.values)
        
        for num in all_numbers:
            if num == 0:
                continue
                
            # Calculate how many digits we need
            if abs(num) >= 1:
                # For numbers >= 1, we need enough digits for the fractional part
                str_repr = f"{num:.15f}".rstrip('0')
                if '.' in str_repr:
                    decimal_part = str_repr.split('.')[1]
                    needed = len(decimal_part) + len(str(int(abs(num))))
                else:
                    needed = len(str(int(abs(num))))
            else:
                # For numbers < 1, we need enough precision for significant digits
                log_val = math.log10(abs(num))
                needed = abs(int(log_val)) + 3  # 3 significant digits minimum
            
            max_precision = max(max_precision, min(needed, 12))  # Cap at 12
        
        return max_precision
    
    def save_to_file(self, filename, use_relative_time=True, precision=6, adaptive_precision=False):
        """
        Save PWL data to a file
        :param filename: Output filename
        :param use_relative_time: Use relative time format
        :param precision: Number of significant digits
        :param adaptive_precision: Auto-determine precision
        :return: True if successful
        """
        try:
            content = self.to_text_precise(use_relative_time, precision, adaptive_precision)
            with open(filename, 'w') as f:
                f.write(content)
            return True
        except Exception as e:
            logging.error(f'PWL save error: {e}')
            return False
    
    def load_from_file(self, pwl_text_file, timestep=None):
        """
        Load PWL data from a file
        :param pwl_text_file: the file path
        :param timestep: the timestep for creating a discrete series (optional)
        :return: True if successful, False otherwise
        """
        if timestep is not None:
            self.timestep = timestep
        
        # Clear existing data
        self.clear()
        
        # check if file exists
        if not os.path.exists(pwl_text_file):
            logging.error('PWL Parser: PWL file not found')
            return False

        # check if text file (allow .pwl and .txt extensions, or if mime type is text)
        mime_type = mimetypes.guess_type(pwl_text_file)[0]
        file_ext = os.path.splitext(pwl_text_file)[1].lower()
        
        if not (mime_type == 'text/plain' or file_ext in ['.txt', '.pwl', '.dat']):
            # Try to read first few bytes to see if it's text
            try:
                with open(pwl_text_file, 'r') as test_file:
                    test_file.read(100)  # Try to read as text
            except UnicodeDecodeError:
                logging.error('PWL Parser: PWL file not in text format')
                return False

        with open(pwl_text_file) as file:
            content = file.read()
            return self.load_from_text(content)
    
    def load_from_text(self, pwl_text):
        """
        Load PWL data from text content
        :param pwl_text: PWL formatted text
        :return: True if successful, False otherwise
        """
        self.clear()
        
        lines = pwl_text.splitlines()

        # check if empty
        if len(lines) == 0:
            logging.error('PWL Parser: PWL text empty')
            return False

        time_last = 0

        for i, line in enumerate(lines):
            arguments = line.split()

            # check if two args per line
            if len(arguments) != 2 and len(arguments) != 0:
                logging.error('PWL Parser: PWL text argument format in line %d' % i)
                return False

            # only parse non-empty lines
            if len(arguments) != 0:
                time_read = ltspice_si_parse(arguments[0])

                # detect if time argument is relative
                is_relative = arguments[0][0] == '+'
                # Store original text representations
                original_time_str = arguments[0].lstrip('+') if is_relative else arguments[0]
                original_value_str = arguments[1]
                
                if is_relative:
                    time_made = time_last + time_read
                    # Store the delta value, not the absolute time
                    point = PwlPoint(original_time_str, original_value_str, is_relative=True)
                else:
                    time_made = time_read
                    point = PwlPoint(original_time_str, original_value_str, is_relative=False)

                self.points.append(point)
                time_last = time_made

        # Check if we have any points before trying to get max
        if len(self.points) == 0:
            logging.warning('PWL Parser: No valid data points found')
            return False

        self._update_discrete()
        
        # Use the timestamps property for logging (which calculates absolute times)
        timestamps = self.timestamps
        logging.info('PWL Parser: PWL data load successful')
        # Guard against empty lists during edge cases
        total_run_time = max(timestamps) if len(timestamps) > 0 else 0.0
        if not self._discrete_dirty and len(self._timestamps_discrete) > 0:
            total_smu_time = max(self._timestamps_discrete)
            discrete_count = len(self._timestamps_discrete)
        else:
            total_smu_time = 0.0
            discrete_count = 0
        logging.info('PWL Parser: Total PWL file run time: %0.3f s' % total_run_time)
        logging.info('PWL Parser: Total SMU run time: %0.3f s' % total_smu_time)
        logging.info('PWL Parser: Nr of points: %d' % discrete_count)

        return True

def discretize(timestamps, values, delta):
    """
    interpolate pwl data and make a discrete series
    :param timestamps: some timestamps
    :param values: the values for those timestamps
    :param delta: time step
    :return: timestamps and values, discrete and evenly timed
    """

    # check lengths
    if len(timestamps) != len(values):
        return None

    values_out = []
    timestamps_out = []

    for timestep in np.arange(0, max(timestamps), delta):
        timestamps_out.append(timestep)
        values_out.append(np.interp(timestep, timestamps, values))

    return timestamps_out, values_out

def PWL_parser(pwl_text_file, timestep):
    """
    Legacy function for backward compatibility
    Loads a LT-Spice styled PWL data file. Also creates a discrete series of samples.
    :param pwl_text_file: the file path
    :param timestep: the timestep for creating a discrete series
    :return: PwlData object or None in case of a fail
    """
    pwl_data = PwlData()
    if pwl_data.load_from_file(pwl_text_file, timestep):
        return pwl_data
    else:
        return None

if __name__ == '__main__':
    import os

    # Test the new class-based approach
    pwl_data = PwlData()
    test_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'examples', 'parser_testfile.txt')
    
    if os.path.exists(test_file) and pwl_data.load_from_file(test_file, 0.002):
        print("Successfully loaded PWL data!")
        print(f"Number of points: {pwl_data.get_point_count()}")
        print("Original points:")
        for i in range(pwl_data.get_point_count()):
            point = pwl_data.get_point(i)
            if point:
                time, value = point
                print(f"  {time:.3f}s, {value:.3f}")
        
        print(f"\nDiscrete points: {len(pwl_data.timestamps_discrete)}")
        print("Values:", pwl_data.values[:5], "..." if len(pwl_data.values) > 5 else "")
        print("Times:", pwl_data.timestamps[:5], "..." if len(pwl_data.timestamps) > 5 else "")
        
        # Test adding a point
        pwl_data.add_point(0.5, 0.1)
        print(f"\nAfter adding point: {pwl_data.get_point_count()} points")
        
        # Test text export
        print("\nExported text:")
        print(pwl_data.to_text())
    else:
        print(f"Failed to load PWL data from: {test_file}")
        print("Please ensure the example file exists in the examples folder.")

    # Test legacy function for backward compatibility
    if os.path.exists(test_file):
        pwl_data_legacy = PWL_parser(test_file, 0.002)
        if pwl_data_legacy:
            print(f"\nLegacy function works: {pwl_data_legacy.get_point_count()} points loaded")
