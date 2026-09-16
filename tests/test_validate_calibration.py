"""
Tests for validate_calibration.py: the schema rules in docs/calibration-data-format.md and
the swap-in of a valid profile as the active config. Everything runs in temp directories,
so the repo's real calibration_profile.json is never touched.

Run from the repo root:  python -m unittest
"""

import copy
import json
import os
import tempfile
import unittest

import validate_calibration as vc

GOOD = [
    {"freq_low": 20,   "freq_high": 200,   "feeling": "rumble",  "pattern": "LOW_RUMBLE"},
    {"freq_low": 200,  "freq_high": 2000,  "feeling": "smooth",  "pattern": "MID_SMOOTH"},
    {"freq_low": 2000, "freq_high": 20000, "feeling": "prickly", "pattern": "HIGH_PRICKLE"},
]


def with_entry(index, **changes):
    """A copy of GOOD with one entry's fields replaced (a value of ... deletes the key)."""
    data = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is ...:
            del data[index][key]
        else:
            data[index][key] = value
    return data


class SchemaErrorsTest(unittest.TestCase):
    def assert_error(self, data, fragment):
        errors, _ = vc.validate_profile(data)
        self.assertTrue(errors, f"expected an error mentioning {fragment!r}, got none")
        self.assertTrue(any(fragment in error for error in errors),
                        f"expected an error mentioning {fragment!r}, got {errors}")

    def test_good_profile_has_no_errors(self):
        errors, warnings = vc.validate_profile(GOOD)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_top_level_must_be_a_non_empty_array(self):
        self.assert_error({"freq_low": 20}, "top level must be a JSON array")
        self.assert_error("nope", "top level must be a JSON array")
        self.assert_error([], "no bands")

    def test_entries_must_be_objects_with_exactly_the_four_keys(self):
        self.assert_error([[20, 200, "x", "X"]], "must be an object")
        self.assert_error(with_entry(0, pattern=...), "missing key(s) pattern")
        self.assert_error(with_entry(1, freq_lo=1), "unexpected key(s) freq_lo")

    def test_frequencies_must_be_finite_non_negative_numbers(self):
        self.assert_error(with_entry(0, freq_low="20"), "freq_low must be a finite number")
        self.assert_error(with_entry(0, freq_low=True), "freq_low must be a finite number")
        self.assert_error(json.loads('[{"freq_low": NaN, "freq_high": 200, "feeling": "x", "pattern": "X"}]'),
                          "freq_low must be a finite number")
        self.assert_error(with_entry(0, freq_low=-5), "must not be negative")

    def test_low_must_be_below_high(self):
        self.assert_error(with_entry(0, freq_low=200, freq_high=200), "must be less than")
        self.assert_error(with_entry(0, freq_low=300, freq_high=200), "must be less than")

    def test_feeling_must_be_a_non_blank_string(self):
        self.assert_error(with_entry(0, feeling=""), "feeling must be a non-empty string")
        self.assert_error(with_entry(0, feeling="   "), "feeling must be a non-empty string")
        self.assert_error(with_entry(0, feeling=7), "feeling must be a non-empty string")

    def test_pattern_must_be_upper_snake_case_and_not_reserved(self):
        for bad in ("short sharp tap", "lower_case", "1ABC", "TAP-1", "", "Tap", None):
            with self.subTest(pattern=bad):
                self.assert_error(with_entry(0, pattern=bad), "UPPER_SNAKE_CASE")
        self.assert_error(with_entry(0, pattern="NONE"), "reserved")
        errors, _ = vc.validate_profile(with_entry(0, pattern="A_1"))
        self.assertEqual(errors, [])

    def test_overlapping_bands_are_an_error_even_when_not_adjacent_in_the_file(self):
        self.assert_error(with_entry(1, freq_low=150), "overlap")
        nested = GOOD + [{"freq_low": 50, "freq_high": 60, "feeling": "x", "pattern": "INSIDE_FIRST"}]
        self.assert_error(nested, "overlap")

    def test_repeated_pattern_names_are_fine(self):
        errors, warnings = vc.validate_profile(with_entry(2, pattern="LOW_RUMBLE"))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class WarningsTest(unittest.TestCase):
    def warnings_for(self, data):
        errors, warnings = vc.validate_profile(data)
        self.assertEqual(errors, [])
        return warnings

    def test_gap_is_a_warning(self):
        warnings = self.warnings_for(with_entry(1, freq_low=300))
        self.assertTrue(any("gap" in w and "200-300" in w for w in warnings), warnings)

    def test_unsorted_is_a_warning(self):
        warnings = self.warnings_for(list(reversed(GOOD)))
        self.assertTrue(any("ascending" in w for w in warnings), warnings)

    def test_above_nyquist_is_a_warning(self):
        warnings = self.warnings_for(with_entry(2, freq_high=30000))
        self.assertTrue(any("22050" in w for w in warnings), warnings)

    def test_touching_bands_have_no_gap_warning(self):
        self.assertEqual(self.warnings_for(GOOD), [])

    def test_placeholder_is_flagged(self):
        with open(vc.PLACEHOLDER_PROFILE_PATH, encoding="utf-8") as f:
            placeholder = json.load(f)
        warnings = self.warnings_for(placeholder)
        self.assertTrue(any("PLACEHOLDER" in w for w in warnings), warnings)


class ActivationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.active = os.path.join(self.tmp.name, "calibration_profile.json")
        self.backup = os.path.join(self.tmp.name, "calibration_profile.backup.json")
        self.write(self.active, [{"freq_low": 0, "freq_high": 1, "feeling": "old", "pattern": "OLD"}])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, data, text=None):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text is not None else json.dumps(data))
        return path

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_valid_profile_is_swapped_in_byte_for_byte_and_old_one_backed_up(self):
        pretty = json.dumps(GOOD, indent=4) + "\n"            # deliberate odd formatting
        source = self.write(os.path.join(self.tmp.name, "mine.json"), None, text=pretty)
        old_active = self.read(self.active)
        self.assertEqual(vc.main([source, "--active", self.active]), 0)
        self.assertEqual(self.read(self.active), pretty)
        self.assertEqual(self.read(self.backup), old_active)
        self.assertEqual(self.read(source), pretty)           # source left in place

    def test_invalid_profile_is_rejected_and_active_untouched(self):
        source = self.write(os.path.join(self.tmp.name, "bad.json"), with_entry(0, pattern="nope"))
        before = self.read(self.active)
        self.assertEqual(vc.main([source, "--active", self.active]), 1)
        self.assertEqual(self.read(self.active), before)
        self.assertFalse(os.path.exists(self.backup))

    def test_check_only_never_writes(self):
        source = self.write(os.path.join(self.tmp.name, "mine.json"), GOOD)
        before = self.read(self.active)
        self.assertEqual(vc.main(["--check-only", source, "--active", self.active]), 0)
        self.assertEqual(self.read(self.active), before)
        self.assertFalse(os.path.exists(self.backup))

    def test_no_argument_rechecks_the_active_profile_without_writing(self):
        self.assertEqual(vc.main(["--active", self.active]), 0)
        self.assertFalse(os.path.exists(self.backup))
        self.write(self.active, with_entry(0, freq_low=-1))
        self.assertEqual(vc.main(["--active", self.active]), 1)

    def test_activating_the_active_file_itself_is_a_no_op(self):
        self.write(self.active, GOOD)
        self.assertEqual(vc.main([self.active, "--active", self.active]), 0)
        self.assertFalse(os.path.exists(self.backup))

    def test_unreadable_and_non_json_files(self):
        self.assertEqual(vc.main([os.path.join(self.tmp.name, "missing.json"), "--active", self.active]), 2)
        broken = self.write(os.path.join(self.tmp.name, "broken.json"), None, text="[{")
        self.assertEqual(vc.main([broken, "--active", self.active]), 1)

    def test_repo_placeholder_validates_and_activates_with_a_warning(self):
        # Activating the placeholder is how you reset; it is allowed but flagged.
        self.assertEqual(vc.main([vc.PLACEHOLDER_PROFILE_PATH, "--active", self.active]), 0)
        self.assertEqual(self.read(self.active), self.read(vc.PLACEHOLDER_PROFILE_PATH))


if __name__ == "__main__":
    unittest.main()
