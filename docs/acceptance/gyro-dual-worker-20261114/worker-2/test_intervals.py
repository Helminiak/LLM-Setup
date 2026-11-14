"""Unittest cases for intervals.merge_intervals (standard library only)."""

import unittest

from intervals import merge_intervals


class MergeIntervalsTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(merge_intervals([]), [])

    def test_empty_interval_dropped(self):
        # start >= end is empty and must be dropped
        self.assertEqual(merge_intervals([(5, 5), (7, 6), (1, 2)]), [(1, 2)])

    def test_touching_intervals_merge(self):
        # half-open: [1,3) and [3,5) touch and merge to [1,5)
        self.assertEqual(merge_intervals([(3, 5), (1, 3)]), [(1, 5)])

    def test_nested_intervals_collapse(self):
        self.assertEqual(merge_intervals([(0, 10), (2, 4), (3, 3), (1, 9)]),
                         [(0, 10)])

    def test_disjoint_intervals_stay_separate(self):
        self.assertEqual(merge_intervals([(10, 12), (0, 2), (5, 6)]),
                         [(0, 2), (5, 6), (10, 12)])

    def test_negative_intervals(self):
        self.assertEqual(merge_intervals([(-5, -3), (-3, -1), (-10, -8)]),
                         [(-10, -8), (-5, -1)])

    def test_unsorted_overlapping_chain(self):
        # chain of overlaps resolves to one interval regardless of input order
        self.assertEqual(merge_intervals([(6, 8), (1, 4), (3, 7), (12, 13)]),
                         [(1, 8), (12, 13)])

    def test_duplicates_collapse(self):
        # exact duplicates must collapse to a single interval
        self.assertEqual(merge_intervals([(2, 4), (2, 4), (2, 4)]), [(2, 4)])

    def test_bad_pair_raises(self):
        with self.assertRaises(ValueError):
            merge_intervals([(1, 2, 3)])


if __name__ == "__main__":
    unittest.main()
