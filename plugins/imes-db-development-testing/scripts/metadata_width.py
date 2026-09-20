"""Shared legacy-grid width rules for generated SYS_TbColumn metadata."""

from __future__ import annotations

from typing import Any


# The active client stores VSFlexGrid widths in 1/15-unit steps. Three Chinese
# characters occupy 840 units, so a full-width display cell is 280 units.
COLUMN_WIDTH_STEP = 15
COLUMN_WIDTH_FULLWIDTH_CHAR = 280


def label_display_cells(label: Any) -> int:
    """Return the legacy display-cell count for a visible field label."""
    text = str(label or "").strip()
    return sum(2 if ord(char) > 0xFF else 1 for char in text)


def label_column_width(label: Any) -> int:
    """Return the smallest grid width that shows the complete field label."""
    cells = label_display_cells(label)
    if cells == 0:
        return COLUMN_WIDTH_STEP
    raw_width = (cells * COLUMN_WIDTH_FULLWIDTH_CHAR + 1) // 2
    return ((raw_width + COLUMN_WIDTH_STEP - 1) // COLUMN_WIDTH_STEP) * COLUMN_WIDTH_STEP
