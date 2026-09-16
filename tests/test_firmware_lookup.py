"""
Checks the CircuitPython sketch (firmware/qtpy_drv2605/code.py) against the laptop prototype,
running it under CPython with the CircuitPython-only modules stubbed out.

Nothing here touches hardware: adafruit_drv2605 is absent, so the sketch's Haptics class
falls into its dry-run branch, and the Controller is exercised with a fake motor driver.
The point is to prove that the board-side calibration lookup is the same lookup as
haptic_prototype.py and that the actuator layer can render every placeholder pattern.

Run from the repo root:  python -m unittest
"""

import importlib.util
import os
import sys
import types
import unittest

import haptic_prototype as hp

FIRMWARE_PATH = os.path.join(hp.REPO_ROOT, "firmware", "qtpy_drv2605", "code.py")


def load_firmware_module():
    """Import the sketch under a private name (never 'code', which is a stdlib module)."""
    for name in ("board", "supervisor"):
        if name not in sys.modules:
            stub = types.ModuleType(name)
            if name == "supervisor":
                stub.runtime = types.SimpleNamespace(serial_bytes_available=0)
            sys.modules[name] = stub
    spec = importlib.util.spec_from_file_location("qtpy_drv2605_firmware", FIRMWARE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fw = load_firmware_module()


class FakeHaptics:
    """Records what the Controller asks the motor to do."""

    def __init__(self):
        self.played = []
        self.stops = 0

    def play(self, pattern):
        self.played.append(pattern)
        return bool(fw.PATTERN_EFFECTS.get(pattern))

    def stop(self):
        self.stops += 1


class LookupMatchesPrototypeTest(unittest.TestCase):
    def setUp(self):
        # The guide tells you to copy the repo's calibration_profile.json onto CIRCUITPY,
        # so that exact file is what the firmware loader is tested against.
        self.fw_profile = fw.load_profile(hp.DEFAULT_PROFILE_PATH)
        self.hp_profile = hp.load_calibration_profile(hp.DEFAULT_PROFILE_PATH)

    def test_both_loaders_produce_identical_tuples(self):
        self.assertEqual(self.fw_profile, self.hp_profile)

    def test_classification_is_identical_across_a_sweep_and_at_every_band_edge(self):
        edges = [low for low, _, _, _ in self.hp_profile] + [self.hp_profile[-1][1]]
        probes = [0.0, 19.99, 22050.0] + list(range(1, 22050, 53))
        for edge in edges:
            probes += [edge - 0.01, edge, edge + 0.01]
        for freq in probes:
            with self.subTest(freq=freq):
                self.assertEqual(
                    fw.classify_frequency(freq, self.fw_profile),
                    hp.classify_frequency(freq, self.hp_profile),
                )

    def test_terminal_line_format_matches_the_prototype(self):
        self.assertEqual(
            fw.format_result(440.0, "sharp, bright, pointed", "SHORT_SHARP_TAP"),
            hp.format_result(440.0, "sharp, bright, pointed", "SHORT_SHARP_TAP"),
        )


class ActuatorLayerTest(unittest.TestCase):
    def test_every_placeholder_pattern_has_a_rendering_entry(self):
        for _, _, _, pattern in hp.load_calibration_profile(hp.PLACEHOLDER_PROFILE_PATH):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, fw.PATTERN_EFFECTS)
        self.assertIn("NONE", fw.PATTERN_EFFECTS)

    def test_effect_sequences_fit_the_drv2605_library_and_sequencer(self):
        for pattern, effects in fw.PATTERN_EFFECTS.items():
            with self.subTest(pattern=pattern):
                self.assertLessEqual(len(effects), 8)          # 8 waveform sequencer slots
                for effect_id in effects:
                    self.assertTrue(1 <= effect_id <= 123)    # 0 is the sequence terminator

    def test_without_hardware_haptics_runs_dry(self):
        haptics = fw.Haptics()
        self.assertTrue(haptics.dry_run)
        self.assertTrue(haptics.play("SHORT_SHARP_TAP"))
        self.assertFalse(haptics.play("UNMAPPED_HIGH"))       # deliberately silent
        self.assertFalse(haptics.play("NOT_A_KNOWN_PATTERN"))
        haptics.stop()                                        # no-op without a driver


class ControllerTest(unittest.TestCase):
    def setUp(self):
        fw.SELFTEST_GAP_SECONDS = 0
        self.profile = fw.load_profile(hp.PLACEHOLDER_PROFILE_PATH)
        self.haptics = FakeHaptics()
        self.controller = fw.Controller(self.profile, self.haptics)

    def test_frequency_line_is_classified_and_played(self):
        message = self.controller.handle_line("1000\r", now=10.0)
        self.assertEqual(message, hp.format_result(1000.0, "sharp, bright, pointed", "SHORT_SHARP_TAP"))
        self.assertEqual(self.haptics.played, ["SHORT_SHARP_TAP"])

    def test_same_band_is_not_retriggered_until_the_retrigger_interval(self):
        self.controller.handle_line("100", now=10.0)
        self.controller.handle_line("150", now=10.1)                          # same band, too soon
        self.assertEqual(self.haptics.played, ["STRONG_SLOW_PULSE"])
        self.controller.handle_line("120", now=10.0 + fw.RETRIGGER_SECONDS + 0.01)   # same band, due again
        self.assertEqual(self.haptics.played, ["STRONG_SLOW_PULSE"] * 2)
        self.controller.handle_line("350", now=10.42)                         # new band, immediate
        self.assertEqual(self.haptics.played[-1], "STEADY_MEDIUM_VIBE")

    def test_motor_stops_after_silence_on_the_wire(self):
        self.controller.handle_line("100", now=10.0)
        self.controller.tick(now=10.2)
        self.assertEqual(self.haptics.stops, 0)
        self.controller.tick(now=10.0 + fw.SILENCE_TIMEOUT_SECONDS + 0.01)
        self.assertEqual(self.haptics.stops, 1)
        self.assertIsNone(self.controller.current_pattern)

    def test_pattern_by_name_selftest_profile_stop_and_garbage(self):
        self.assertIn("played by name", self.controller.handle_line("STRONG_SLOW_PULSE", now=1.0))
        self.assertEqual(self.haptics.played[-1], "STRONG_SLOW_PULSE")

        self.assertEqual(self.controller.handle_line("selftest", now=2.0), "selftest done")
        self.assertEqual(self.haptics.played[-5:], [pattern for _, _, _, pattern in self.profile])

        listing = self.controller.handle_line("profile", now=3.0)
        for _, _, _, pattern in self.profile:
            self.assertIn(pattern, listing)

        stops_before = self.haptics.stops
        self.assertEqual(self.controller.handle_line("STOP", now=4.0), "stopped")
        self.assertEqual(self.haptics.stops, stops_before + 1)

        self.assertIn("unrecognized", self.controller.handle_line("banana", now=5.0))
        self.assertIsNone(self.controller.handle_line("   ", now=6.0))


if __name__ == "__main__":
    unittest.main()
