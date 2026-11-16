"""Colours and sizes shared by every chart, so all figures read as one system.

Rules followed (see also docs/ARCHITECTURE.md, "Charts"):
* Series colours are used in this fixed order and never cycled; a colour
  belongs to a signal (e.g. front-left wheel), not to its position in a list.
* Status colours are reserved for good/warning/critical states (a lifted
  wheel is "critical") and are always paired with a text label.
* One y-axis per chart; signals with different units go in separate charts
  stacked on a shared time axis.
"""

from __future__ import annotations

# Categorical series colours (colour-blind-checked order).
SERIES: tuple[str, ...] = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                           "#6250d6", "#e34948")
# One-hue ramp for magnitudes (light = little, dark = much), e.g. wheel load.
SEQUENTIAL: tuple[str, ...] = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#104281")
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"
NEUTRAL = "#8a8983"
# Line styles that tell runs apart when several runs share a chart.
RUN_DASHES: tuple[str, ...] = ("solid", "dash", "dot", "dashdot")
LINE_WIDTH = 2
MAX_POINTS = 4000  # samples per line sent to the browser (longer runs are thinned)


def sequential_colour(fraction: float) -> str:
    """Colour of the magnitude ramp for a value between 0 (little) and 1 (much)."""
    clipped = min(1.0, max(0.0, fraction))
    return SEQUENTIAL[min(len(SEQUENTIAL) - 1, int(clipped * len(SEQUENTIAL)))]
