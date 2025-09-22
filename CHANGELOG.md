## 1.4 - 2025-09-22

Enhancements
- Plot selection box (Table-only): added robust event lifecycle and border clamping
- Repeated box selection: fixed stale rectangle cleanup; rectangle can be drawn multiple times

Fixes
- Undo safety: replaced unintended update_plot() calls in selection/table handlers with _update_plot_internal()
- Border interactions: clamped pixel coords to axes for drag/move/release, enabling selection when releasing outside plot
- Undo edge case: guarded max() logging in parser to avoid errors on empty datasets

Internal
- Connected/disconnected matplotlib events on tab changes; initial connect when starting in Table mode
- Added GPT-5 (OpenAI) to AI Tools attribution

# Changelog

## Version 1.3 (2025-09-22)

### Undo/Redo
- **Undo/Redo support** - Standard Ctrl+Z/Y keyboard shortcuts for all operations
- **Smart text handling** - Undo discards invalid text and restores last valid state

## Version 1.2 (2025-09-20)

### Export Format Settings
- **Export format dropdown** - Choose format applied when saving files (Preserve Mixed, Force Relative, Force Absolute)
- **MicroCap compatibility** - Force Absolute format required for MicroCap compatibility

## Version 1.1 (2025-09-20)

### Smart Point Insertion
- **Add Above/Below** - Insert points with intelligent time suggestions
- **Clean value suggestions** - Suggests readable values like "50m" instead of "0.0500015"
- **Notation preservation** - Respects your preferred time formats (SI prefixes, scientific, decimal)
- **Gap-aware calculations** - Handles large gaps intelligently
- **Always ordered** - Ensures new points maintain chronological order

### Enhanced Multi-Selection & Editing
- **Plot highlighting** - Selected table rows are highlighted in the plot
- **Multi-row selection** - Select multiple rows with Ctrl+Click
- **Bulk editing** - Edit values across multiple selected rows
- **Smart Type conversion** - Convert ABS ↔ REL while preserving notation
- **Selection preservation** - Multi-selection is preserved during editing

### Format Conversion Tools
- **Time format conversion** - Convert between SI prefix and scientific notation
- **Value format conversion** - Convert values between different notations  
- **ABS/REL conversion** - Convert between absolute and relative time with notation preservation
- **Bulk format operations** - Apply formatting to entire datasets
- **Original format restoration** - Restore to original imported formatting

## Version 1.0 (2025-09-20)

### Initial Release
- Professional PWL file editor with table-based interface
- Real-time waveform plotting with matplotlib
- Smart ABS/REL time format conversion preserving waveform integrity
- Inline cell editing for time, value, and format columns
- Text editor with syntax validation and real-time updates
- Multi-selection operations (delete, move up/down)
- Import/Export functionality for PWL files
- Clean architecture with separated GUI geometry and application logic
- SI unit prefix support (k, m, u, n, etc.)

### Technical Features
- Format-aware data model with PwlPoint class
- Callback-based architecture for clean separation of concerns
- Real-time validation and error handling
- Professional code structure suitable for open source release

### AI Development
- Developed with assistance from Claude Sonnet 4 (Anthropic)
- Architectural design and code optimization
