"""
Synthetic-frequency test of the Phase 1 pipeline: FFT -> dominant frequency -> calibration lookup.

No microphone, no sounddevice, no PortAudio. Blocks of known sine waves are generated with
numpy and pushed through the same function the live mic callback uses (process_block), so a
pass here proves the pipeline logic independently of any audio hardware.

Run from the repo root:  python -m unittest
"""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

import haptic_prototype as hp

# Frequency resolution of one FFT block (~43 Hz). A pure tone lands in the nearest bin, so the
# detected frequency can legitimately differ from the true one by up to this much.
FFT_BIN_HZ = hp.SAMPLE_RATE / hp.BLOCK_SIZE

# The data that used to be hardcoded as CALIBRATION_PROFILE, now in profiles/placeholder.json.
ORIGINAL_PLACEHOLDER = [
    (20,    200,   "rough, gravelly, in your gut",     "STRONG_SLOW_PULSE"),
    (200,   500,   "smooth, rounded",                   "STEADY_MEDIUM_VIBE"),
    (500,   2000,  "sharp, bright, pointed",             "SHORT_SHARP_TAP"),
    (2000,  8000,  "thin, glassy, high in the chest",    "FAST_LIGHT_FLUTTER"),
    (8000,  20000, "not yet mapped",                     "UNMAPPED_HIGH"),
]


def sine_block(freq_hz, amplitude=0.5, frames=hp.BLOCK_SIZE, sample_rate=hp.SAMPLE_RATE):
    """One (frames, 1) block of a pure tone, shaped like the indata sounddevice delivers."""
    t = np.arange(frames) / sample_rate
    samples = amplitude * np.sin(2 * np.pi * freq_hz * t)
    return samples.astype(np.float32).reshape(-1, 1)


class ImportIsHardwareFreeTest(unittest.TestCase):
    def test_importing_the_prototype_does_not_import_sounddevice(self):
        # The whole point of this test module: the pipeline logic must not need PortAudio.
        self.assertNotIn("sounddevice", sys.modules)


class DominantFrequencyTest(unittest.TestCase):
    def test_pure_tones_are_detected_within_one_fft_bin(self):
        for freq in (60, 100, 350, 1000, 1500, 4000, 12000, 19000):
            with self.subTest(freq=freq):
                detected = hp.dominant_frequency(sine_block(freq)[:, 0])
                self.assertLessEqual(abs(detected - freq), FFT_BIN_HZ)

    def test_louder_tone_wins_in_a_mixture(self):
        block = sine_block(100, amplitude=0.2) + sine_block(3000, amplitude=0.6)
        detected = hp.dominant_frequency(block[:, 0])
        self.assertLessEqual(abs(detected - 3000), FFT_BIN_HZ)

    def test_all_zero_block_reports_dc(self):
        # Documents current behaviour: a silent block has its (zero) maximum at bin 0,
        # which classifies as ("unknown", "NONE") with any sane profile.
        silence = np.zeros(hp.BLOCK_SIZE, dtype=np.float32)
        self.assertEqual(hp.dominant_frequency(silence), 0.0)


class ClassifyFrequencyTest(unittest.TestCase):
    PROFILE = [
        (20,  200,  "low",  "LOW"),
        (200, 500,  "mid",  "MID"),
        (500, 2000, "high", "HIGH"),
    ]

    def test_bands_are_half_open_low_inclusive_high_exclusive(self):
        self.assertEqual(hp.classify_frequency(20, self.PROFILE), ("low", "LOW"))
        self.assertEqual(hp.classify_frequency(199.99, self.PROFILE), ("low", "LOW"))
        self.assertEqual(hp.classify_frequency(200, self.PROFILE), ("mid", "MID"))
        self.assertEqual(hp.classify_frequency(499.5, self.PROFILE), ("mid", "MID"))
        self.assertEqual(hp.classify_frequency(500, self.PROFILE), ("high", "HIGH"))

    def test_outside_every_band_is_unknown_none(self):
        for freq in (0.0, 5, 19.99, 2000, 22050):
            with self.subTest(freq=freq):
                self.assertEqual(hp.classify_frequency(freq, self.PROFILE), ("unknown", "NONE"))

    def test_first_matching_entry_wins_when_bands_overlap(self):
        overlapping = [(0, 1000, "a", "A"), (500, 2000, "b", "B")]
        self.assertEqual(hp.classify_frequency(700, overlapping), ("a", "A"))

    def test_empty_profile_maps_everything_to_none(self):
        self.assertEqual(hp.classify_frequency(440, []), ("unknown", "NONE"))


class ProfileFileTest(unittest.TestCase):
    def test_active_profile_loads_as_low_high_feeling_pattern_tuples(self):
        profile = hp.load_calibration_profile()
        self.assertGreater(len(profile), 0)
        for low, high, feeling, pattern in profile:
            self.assertLess(low, high)
            self.assertIsInstance(feeling, str)
            self.assertIsInstance(pattern, str)

    def test_placeholder_file_is_exactly_the_original_hardcoded_data(self):
        profile = hp.load_calibration_profile(hp.PLACEHOLDER_PROFILE_PATH)
        self.assertEqual(profile, ORIGINAL_PLACEHOLDER)
        self.assertTrue(hp.is_placeholder_profile(profile))

    def test_a_different_profile_is_not_flagged_as_placeholder(self):
        self.assertFalse(hp.is_placeholder_profile([(20, 20000, "everything", "ONE_PATTERN")]))

    def test_malformed_profiles_are_rejected_with_a_hint(self):
        bad_files = {
            "not_an_array": {"freq_low": 20, "freq_high": 200, "feeling": "x", "pattern": "X"},
            "missing_key": [{"freq_low": 20, "freq_high": 200, "feeling": "x"}],
            "not_an_object": [[20, 200, "x", "X"]],
        }
        for name, content in bad_files.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, f"{name}.json")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(content, f)
                    with self.assertRaises(ValueError) as ctx:
                        hp.load_calibration_profile(path)
                    self.assertIn("validate_calibration.py", str(ctx.exception))


class EndToEndSyntheticTest(unittest.TestCase):
    """The whole pipeline minus the microphone: synthetic block -> process_block -> pattern."""

    def setUp(self):
        self.profile = hp.load_calibration_profile(hp.PLACEHOLDER_PROFILE_PATH)

    def test_a_tone_in_each_placeholder_band_reaches_that_bands_pattern(self):
        expectations = [
            (100,   "STRONG_SLOW_PULSE"),
            (350,   "STEADY_MEDIUM_VIBE"),
            (1000,  "SHORT_SHARP_TAP"),
            (4000,  "FAST_LIGHT_FLUTTER"),
            (12000, "UNMAPPED_HIGH"),
        ]
        for freq, expected_pattern in expectations:
            with self.subTest(freq=freq):
                detected, feeling, pattern = hp.process_block(sine_block(freq), self.profile)
                self.assertEqual(pattern, expected_pattern)
                self.assertLessEqual(abs(detected - freq), FFT_BIN_HZ)
                self.assertEqual(feeling, hp.classify_frequency(freq, self.profile)[0])

    def test_sweep_of_tones_classifies_like_the_true_frequency(self):
        # Tones closer than one FFT bin to a band edge may quantize into the neighbouring
        # band; that is expected behaviour, so skip them and check everything else.
        edges = [low for low, _, _, _ in self.profile] + [self.profile[-1][1]]
        checked = 0
        for freq in range(50, 20000, 137):
            if min(abs(freq - edge) for edge in edges) <= FFT_BIN_HZ:
                continue
            with self.subTest(freq=freq):
                _, feeling, pattern = hp.process_block(sine_block(freq), self.profile)
                self.assertEqual((feeling, pattern), hp.classify_frequency(freq, self.profile))
            checked += 1
        self.assertGreater(checked, 100)

    def test_stereo_input_uses_channel_zero(self):
        stereo = np.hstack([sine_block(100), sine_block(4000)])   # left: bass, right: treble
        _, _, pattern = hp.process_block(stereo, self.profile)
        self.assertEqual(pattern, "STRONG_SLOW_PULSE")

    def test_silence_falls_through_to_none(self):
        silence = np.zeros((hp.BLOCK_SIZE, 1), dtype=np.float32)
        self.assertEqual(hp.process_block(silence, self.profile), (0.0, "unknown", "NONE"))

    def test_terminal_line_format_is_unchanged(self):
        line = hp.format_result(440.0, "sharp, bright, pointed", "SHORT_SHARP_TAP")
        self.assertEqual(line, "  440.0 Hz  ->  SHORT_SHARP_TAP       (sharp, bright, pointed)")


if __name__ == "__main__":
    unittest.main()
