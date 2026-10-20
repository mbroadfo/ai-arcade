"""Geometry checks on a decoded length-n vector.

The vector is already built. These helpers only read that vector. They do not
load a ROM or a core.
"""
from __future__ import annotations


def split_vector(vector: list[float], width: int, height: int) -> tuple[list[list[int]], list[float]]:
    cells = width * height
    if len(vector) != cells + height:
        raise ValueError(f"vector length {len(vector)} does not match {width} by {height}")
    rows = []
    for row in range(height):
        start = row * width
        rows.append([int(vector[start + col]) for col in range(width)])
    return rows, [float(value) for value in vector[cells:]]


def one_hot_index(row: list[float]) -> int | None:
    hits = [index for index, value in enumerate(row) if value == 1.0]
    if len(hits) != 1:
        return None
    if any(value not in (0.0, 1.0) for value in row):
        return None
    return hits[0]


def pipe_columns(rows: list[list[int]], ground_index: int) -> list[int]:
    """Forward columns with solids on the body row and the row above it.

    The one-hot row is Mario's body, not the brick floor. A two-high pipe
    stands on that floor, so it occupies the body row and the row above.
    """
    if ground_index is None or not rows:
        return []
    lower = ground_index
    upper = ground_index - 1
    if upper < 0 or lower >= len(rows):
        return []
    found = []
    for offset in range(1, len(rows[0])):
        if rows[upper][offset] == 1 and rows[lower][offset] == 1:
            found.append(offset)
    return found


def floor_solid(rows: list[list[int]], ground_index: int) -> bool:
    """Column 0 of the row under the one-hot. That row is the brick floor."""
    if ground_index is None or not rows:
        return False
    floor_row = ground_index + 1
    if not 0 <= floor_row < len(rows):
        return False
    return rows[floor_row][0] == 1


def air_above(rows: list[list[int]], ground_index: int, columns: list[int]) -> bool:
    """True when every cell above a two-high run is empty. No run means no air failure."""
    if not columns or ground_index is None:
        return True
    top = ground_index - 1
    if top <= 0:
        return True
    for offset in columns:
        for row in range(top):
            if rows[row][offset] != 0:
                return False
    return True


def solid_below(rows: list[list[int]], row_index: int, col: int = 0) -> bool:
    if row_index is None or not rows or not 0 <= row_index < len(rows):
        return False
    return any(rows[lower][col] == 1 for lower in range(row_index + 1, len(rows)))
