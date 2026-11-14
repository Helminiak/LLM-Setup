"""Merge half-open integer intervals [start, end).

Standard library only. Intervals with start >= end are treated as empty
and dropped. Merging joins intervals that overlap or touch (e.g.
[1, 3) and [3, 5) merge into [1, 5)).
"""

from typing import Iterable, List, Sequence, Tuple

Interval = Tuple[int, int]


def merge_intervals(intervals: Iterable[Sequence[int]]) -> List[Interval]:
    """Return a sorted list of maximal disjoint non-touching half-open
    intervals covering exactly the non-empty inputs.

    >>> merge_intervals([(3, 5), (1, 3), (10, 12)])
    [(1, 5), (10, 12)]
    >>> merge_intervals([])
    []
    """
    normalized: List[Interval] = []
    for iv in intervals:
        if len(iv) != 2:
            raise ValueError("each interval must be a (start, end) pair")
        start, end = int(iv[0]), int(iv[1])
        if start < end:  # drop empty intervals
            normalized.append((start, end))
    if not normalized:
        return []
    normalized.sort()
    merged: List[Interval] = [normalized[0]]
    for start, end in normalized[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:  # overlap or touch
            if end > last_end:
                merged[-1] = (last_start, end)
        else:
            merged.append((start, end))
    return merged
