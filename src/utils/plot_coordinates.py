"""
Plot coordinate utilities for the PWL Editor.
Author: markus(at)schrodt.at
AI Tools: GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

from typing import Optional, Tuple

def data_to_pixel(ax, data_x: float, data_y: float) -> Tuple[Optional[float], Optional[float]]:
    try:
        if ax is None:
            return None, None
        pixel_coords = ax.transData.transform([(data_x, data_y)])
        return pixel_coords[0][0], pixel_coords[0][1]
    except Exception:
        return None, None


def pixel_to_data(ax, pixel_x: float, pixel_y: float) -> Tuple[Optional[float], Optional[float]]:
    try:
        if ax is None:
            return None, None
        data_coords = ax.transData.inverted().transform([(pixel_x, pixel_y)])
        return data_coords[0][0], data_coords[0][1]
    except Exception:
        return None, None


def clamp_pixel_to_axes(ax, px: float, py: float) -> Tuple[float, float]:
    try:
        if ax is None:
            return px, py
        bbox = ax.get_window_extent()
        clamped_x = min(max(px, bbox.x0), bbox.x1)
        clamped_y = min(max(py, bbox.y0), bbox.y1)
        return clamped_x, clamped_y
    except Exception:
        return px, py
