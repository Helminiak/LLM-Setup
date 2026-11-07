//! Clamp an `i32` into an inclusive `[lo, hi]` range, standard library only.

/// Returns `value` constrained to the inclusive range `[lo, hi]`.
///
/// Values below `lo` collapse to `lo`, values above `hi` collapse to `hi`,
/// and values already inside the range are returned unchanged.
///
/// # Panics
///
/// Panics when `lo > hi`, because such a range cannot contain any value.
pub fn clamp(value: i32, lo: i32, hi: i32) -> i32 {
    assert!(
        lo <= hi,
        "clamp bounds reversed: lo ({lo}) must be <= hi ({hi})"
    );

    if value < lo {
        lo
    } else if value > hi {
        hi
    } else {
        value
    }
}

fn main() {
    for value in [-7_i32, 0, 5, 99] {
        println!("clamp({value}, 1, 10) = {}", clamp(value, 1, 10));
    }
}

#[cfg(test)]
mod tests {
    use super::clamp;

    #[test]
    fn normal_values_pass_through_unchanged() {
        assert_eq!(clamp(5, 1, 10), 5);
        assert_eq!(clamp(7, 1, 10), 7);
    }

    #[test]
    fn lower_boundary_is_inclusive_and_saturates_below() {
        assert_eq!(clamp(1, 1, 10), 1);
        assert_eq!(clamp(-100, 1, 10), 1);
    }

    #[test]
    fn upper_boundary_is_inclusive_and_saturates_above() {
        assert_eq!(clamp(10, 1, 10), 10);
        assert_eq!(clamp(100, 1, 10), 10);
    }

    #[test]
    fn equal_bounds_collapse_to_the_single_value() {
        assert_eq!(clamp(4, 4, 4), 4);
        assert_eq!(clamp(0, 4, 4), 4);
        assert_eq!(clamp(9, 4, 4), 4);
    }

    #[test]
    fn negative_ranges_clamp_in_both_directions() {
        assert_eq!(clamp(-5, -10, -1), -5);
        assert_eq!(clamp(-20, -10, -1), -10);
        assert_eq!(clamp(3, -10, -1), -1);
    }

    #[test]
    #[should_panic(expected = "clamp bounds reversed")]
    fn reversed_bounds_panic() {
        let _ = clamp(5, 10, 1);
    }
}
