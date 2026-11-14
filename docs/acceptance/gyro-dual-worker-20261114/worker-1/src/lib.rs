//! Deterministic closed integer interval overlap length.
//!
//! An interval `[lo, hi]` with `i64` bounds represents all integers `x` with
//! `lo <= x <= hi`. Bounds are given as `i64`; the overlap length is returned
//! as `u64` because a closed overlap of `n` integers has `n >= 0` elements.

/// Returns the number of integers contained in the intersection of the two
/// closed intervals `[a_lo, a_hi]` and `[b_lo, b_hi]`.
///
/// Returns `None` if either interval is malformed (`lo > hi`), or if the
/// overlap length is unrepresentable in `u64`: the full i64 range holds
/// `2^64` integers, which exceeds `u64::MAX`.
///
/// ```
/// use gyro_acceptance_one::overlap_len;
/// assert_eq!(overlap_len(0, 9, 5, 14), Some(5)); // 5..=9
/// assert_eq!(overlap_len(0, 4, 5, 9), Some(0));  // disjoint
/// assert_eq!(overlap_len(i64::MIN, i64::MAX, i64::MIN, i64::MIN), Some(1));
/// assert_eq!(overlap_len(i64::MIN, i64::MAX, i64::MIN, i64::MAX), None);
/// ```
pub fn overlap_len(a_lo: i64, a_hi: i64, b_lo: i64, b_hi: i64) -> Option<u64> {
    if a_lo > a_hi || b_lo > b_hi {
        return None;
    }
    let lo = a_lo.max(b_lo);
    let hi = a_hi.min(b_hi);
    if lo > hi {
        return Some(0);
    }
    // Closed intervals are inclusive: the count of integers in `lo..=hi`
    // is `hi - lo + 1`. Widen to i128 because `hi - lo + 1` reaches 2^64
    // for the full i64 range; `u64::try_from` then yields None for the one
    // unrepresentable length instead of overflowing.
    let len = (hi as i128) - (lo as i128) + 1;
    u64::try_from(len).ok()
}

#[cfg(test)]
mod tests {
    use super::overlap_len;

    #[test]
    fn partial_overlap_counts_inclusive_end() {
        // 5..=9 has 5 integers.
        assert_eq!(overlap_len(0, 9, 5, 14), Some(5));
    }

    #[test]
    fn disjoint_intervals_have_zero_overlap() {
        assert_eq!(overlap_len(0, 4, 5, 9), Some(0));
    }

    #[test]
    fn single_point_touch_counts_one() {
        assert_eq!(overlap_len(0, 5, 5, 10), Some(1));
    }

    #[test]
    fn identical_intervals_count_whole_span() {
        assert_eq!(overlap_len(-3, 3, -3, 3), Some(7));
    }

    #[test]
    fn containment_returns_inner_length() {
        assert_eq!(overlap_len(0, 100, 40, 42), Some(3));
    }

    #[test]
    fn negative_lo_malformed_returns_none() {
        assert_eq!(overlap_len(5, 1, 0, 10), None);
        assert_eq!(overlap_len(0, 10, 9, 2), None);
    }

    #[test]
    fn wide_negative_span_is_exact() {
        // Overlap of [-1_000_000..=-999_990] with [-999_995..=0] is
        // -999_995..=-999_990 => 6 integers.
        assert_eq!(overlap_len(-1_000_000, -999_990, -999_995, 0), Some(6));
    }

    #[test]
    fn min_boundary_single_element_overlap() {
        // Intersection is the single point MIN..=MIN => 1 integer.
        assert_eq!(overlap_len(i64::MIN, i64::MAX, i64::MIN, i64::MIN), Some(1));
        assert_eq!(overlap_len(i64::MIN, i64::MAX, i64::MAX, i64::MAX), Some(1));
    }

    #[test]
    fn full_range_overlap_length_unrepresentable_returns_none() {
        // Full i64 range holds 2^64 elements, which cannot fit in u64.
        assert_eq!(overlap_len(i64::MIN, i64::MAX, i64::MIN, i64::MAX), None);
    }
}
