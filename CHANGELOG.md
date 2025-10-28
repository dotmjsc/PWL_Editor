# Changelog

## Version 2.0 (2025-10-28)
### Waveform Workflows
- Waveform Repair tool flags duplicate timestamps and time reversals, lets you preview the fix, and applies the cleanup in one click.
- Square, triangle, and saw generators guide you through parameter entry, guard against impossible ramps, and can emit relative timestamps for easier merging.
- Triangle generator now uses an intuitive `symmetry` slider so you can rebalance ramps without duty-cycle math.

### Exporting & Formatting
- Export options live in the menu with clear presets for relative, absolute, or mixed formats, and the editor now confirms saves and exports with status messages.
- Conversion settings moved into the menu and respect table selections, so you can reformat only the rows you highlighted.
- Formatting polish keeps units readable from femto to milli, avoiding sudden jumps into scientific notation.

### Editing Polish
- Smart insertion suggestions land safely between their neighbours and respect rounding, making auto-suggested values trustworthy.
- Undo/redo stays clean after opening or creating files, so rolling back always hits the right baseline.
- `Ctrl+A` selects the entire table and the unused plot legend is gone for a cleaner chart.

### Behind the Scenes
- The editor core is now split into focused controllers and services, delivering a snappier UI, tighter sync between table/text/plot views, and a sturdier base for new tools.

## Version 1.4 (2025-09-22)
### Enhancements
- Plot selection box (Table-only): added robust event lifecycle and border clamping.
- Repeated box selection: fixed stale rectangle cleanup; rectangle can be drawn multiple times.

### Fixes
- Undo safety: replaced unintended `update_plot()` calls in selection/table handlers with `_update_plot_internal()`.
- Border interactions: clamped pixel coordinates to axes for drag/move/release, enabling selection when releasing outside the plot.
- Undo edge case: guarded `max()` logging in parser to avoid errors on empty datasets.

### Internal
- Connected/disconnected matplotlib events on tab changes; initial connect when starting in Table mode.
- Added GPT-5 (OpenAI) to AI Tools attribution.

## Version 1.3 (2025-09-22)

### Undo/Redo
- Added standard Ctrl+Z/Ctrl+Y shortcuts for all operations.
- Undo now discards invalid text and restores the last valid state.

## Version 1.2 (2025-09-20)

### Export Format Settings
- Added an export format dropdown to choose between Preserve Mixed, Force Relative, or Force Absolute when saving files.
- Documented that Force Absolute remains required for MicroCap compatibility.

## Version 1.1 (2025-09-20)

### Smart Point Insertion
- Added Add Above/Below commands that insert points with intelligent time suggestions.
- Improved value suggestions to prefer readable outputs such as "50 m" instead of "0.0500015".
- Preserved original time notation, whether SI prefixes, scientific, or decimal formats.
- Made insertion calculations gap-aware so large intervals stay well behaved.
- Kept newly inserted points in chronological order automatically.

### Enhanced Multi-Selection & Editing
- Highlighted table selections directly on the plot.
- Enabled multi-row selection via Ctrl+Click.
- Added bulk editing for multiple selected rows.
- Converted between ABS and REL while preserving notation.
- Preserved multi-selection during edit cycles.

### Format Conversion Tools
- Converted time values between SI prefixes and scientific notation.
- Converted value fields between supported notations.
- Converted between absolute and relative time while preserving notation.
- Applied formatting options to entire datasets in one step.
- Restored original formatting from imported files when needed.

## Version 1.0 (2025-09-20)

### Initial Release
- Released a professional PWL file editor with a table-based interface.
- Added real-time waveform plotting powered by matplotlib.
- Implemented smart ABS/REL time format conversion that preserves waveform integrity.
- Enabled inline cell editing for time, value, and format columns.
- Included a text editor with syntax validation and real-time updates.
- Provided multi-selection operations for delete and move up/down.
- Delivered import and export functionality for PWL files.
- Structured the project with separated GUI geometry and application logic.
- Added SI unit prefix support for k, m, µ, n, and more.

### Technical Features
- Introduced a format-aware data model with the `PwlPoint` class.
- Adopted a callback-based architecture for clear separation of concerns.
- Added real-time validation and error handling throughout the editor.
- Maintained a professional code structure suitable for open-source release.

### AI Development
- Developed with assistance from Claude Sonnet 4 (Anthropic).
- Refined architectural design and code optimizations based on AI input.
