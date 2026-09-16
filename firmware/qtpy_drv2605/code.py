"""
Phase 2 prep: CircuitPython sketch for an Adafruit QT Py + DRV2605L haptic motor controller.

Save this file on the CIRCUITPY drive as code.py. Wiring and setup: docs/hardware-setup.md.

It is the same pipeline as haptic_prototype.py, with the microphone and the FFT left on
the laptop for now:

    laptop:  mic -> FFT -> dominant frequency (Hz)
                                 |  USB serial, one number per line
    QT Py:                       v
             frequency -> calibration_profile.json lookup -> pattern -> DRV2605L effect -> motor

classify_frequency() below is a copy of the one in haptic_prototype.py, and it reads the
SAME calibration_profile.json -- copy that file onto CIRCUITPY next to this one.

Two layers, deliberately kept apart:

  * calibration_profile.json   the PERSONAL layer. Which sound maps to which felt pattern,
                               calibrated to one specific person's own synesthetic
                               association. This is the part of the project that matters.
                               The copy shipped in the repo is placeholder data.
  * PATTERN_EFFECTS (below)    the ACTUATOR layer. How this particular motor renders a named
                               pattern, as DRV2605L waveform-library effect IDs. Generic
                               engineering; tune it by feel.

No hardware is assumed. If the DRV2605L or its library is missing, the sketch runs in
DRY-RUN mode and prints what it would have played, so the lookup can still be exercised
from the serial console.

Serial console commands (type them in the CircuitPython serial console, or send them from
a script; one per line):

    440                classify 440 Hz with the profile and play its pattern
    SHORT_SHARP_TAP    play a pattern by name, to judge the actuator layer by feel
    selftest           play every pattern in the profile once, in profile order
    profile            print the loaded profile
    stop               stop the motor
"""

import json
import sys
import time

import board
import supervisor

PROFILE_PATH = "/calibration_profile.json"

# "ERM" for the vibrating mini motor disc. Switch to "LRA" only after reading the LRA notes
# in docs/hardware-setup.md -- LRAs need the DRV2605L's auto-calibration for their resonant
# frequency, which this first build deliberately avoids.
MOTOR_TYPE = "ERM"

# While frequencies in the same band keep arriving, re-trigger that pattern this often
# (the library effects are one-shots). Stop the motor after this much silence on the wire.
RETRIGGER_SECONDS = 0.35
SILENCE_TIMEOUT_SECONDS = 0.5
SELFTEST_GAP_SECONDS = 1.0

# ---- actuator layer: pattern name -> DRV2605L waveform-library effect IDs ----
# IDs 1-123 from the DRV2605L datasheet "Waveform Library Effects List" (ERM libraries).
# A list is a sequence played back to back (max 8). An empty list is deliberately silent.
# These are FIRST GUESSES for the placeholder pattern names. Tune them by feel in Phase 2,
# and add an entry for every pattern name your own profile uses.
PATTERN_EFFECTS = {
    "STRONG_SLOW_PULSE":  [52],   # 52: Pulsing Strong 1 - 100%
    "STEADY_MEDIUM_VIBE": [48],   # 48: Buzz 2 - 80%
    "SHORT_SHARP_TAP":    [4],    #  4: Sharp Click - 100%
    "FAST_LIGHT_FLUTTER": [57],   # 57: Pulsing Sharp 2 - 60%
    "UNMAPPED_HIGH":      [],     # silent: the profile says "not yet mapped"
    "NONE":               [],     # silent: frequency outside every band
}


def load_profile(path=PROFILE_PATH):
    """Read the profile JSON into (low_hz, high_hz, feeling, pattern) tuples.

    Same shape as load_calibration_profile() in haptic_prototype.py.
    """
    with open(path) as f:
        entries = json.load(f)
    return [(e["freq_low"], e["freq_high"], e["feeling"], e["pattern"]) for e in entries]


def classify_frequency(freq_hz, profile):
    """Same rule as haptic_prototype.classify_frequency: half-open bands, first match wins."""
    for low, high, feeling, pattern in profile:
        if low <= freq_hz < high:
            return feeling, pattern
    return "unknown", "NONE"


def format_result(freq, feeling, pattern):
    """Same terminal line as the laptop prototype prints."""
    return "{:7.1f} Hz  ->  {:20s}  ({})".format(freq, pattern, feeling)


class Haptics:
    """Drives the DRV2605L, or prints instead when there is no hardware (dry run)."""

    def __init__(self):
        self.drv = None
        self.effect_cls = None
        try:
            import adafruit_drv2605
        except ImportError:
            print("adafruit_drv2605 is not in /lib  ->  DRY RUN (printing instead of vibrating)")
            return
        try:
            try:
                i2c = board.STEMMA_I2C()   # the STEMMA QT connector (its own bus on QT Py RP2040)
            except AttributeError:
                i2c = board.I2C()          # boards whose connector shares the main SDA/SCL pins
            drv = adafruit_drv2605.DRV2605(i2c)
        except (RuntimeError, ValueError, OSError) as exc:
            print("No DRV2605L answered on I2C ({})  ->  DRY RUN".format(exc))
            return
        if MOTOR_TYPE == "LRA":
            drv.use_LRM()
            drv.library = adafruit_drv2605.LIBRARY_LRA
        else:
            drv.use_ERM()
            drv.library = adafruit_drv2605.LIBRARY_TS2200A
        self.drv = drv
        self.effect_cls = adafruit_drv2605.Effect
        print("DRV2605L found; motor type {}".format(MOTOR_TYPE))

    @property
    def dry_run(self):
        return self.drv is None

    def play(self, pattern):
        """Render one named pattern. Returns True if something was (or would be) played."""
        effects = PATTERN_EFFECTS.get(pattern)
        if effects is None:
            print("  no PATTERN_EFFECTS entry for {} -- add one to render it".format(pattern))
            return False
        if not effects:
            self.stop()
            return False
        if self.dry_run:
            print("  [dry run] would play effect sequence {} for {}".format(effects, pattern))
            return True
        self.drv.stop()
        for slot in range(8):
            effect_id = effects[slot] if slot < len(effects) else 0   # 0 ends the sequence
            self.drv.sequence[slot] = self.effect_cls(effect_id)
        self.drv.play()
        return True

    def stop(self):
        if not self.dry_run:
            self.drv.stop()


class Controller:
    """Turns serial lines into lookups and motor triggers."""

    def __init__(self, profile, haptics):
        self.profile = profile
        self.haptics = haptics
        self.current_pattern = None
        self.last_input = None
        self.last_trigger = 0.0
        self.profile_patterns = [pattern for _, _, _, pattern in profile]
        for pattern in self.profile_patterns:
            if pattern not in PATTERN_EFFECTS:
                print("WARNING: profile pattern {} has no PATTERN_EFFECTS entry; it will be silent".format(pattern))

    def handle_line(self, line, now):
        """Handle one console line. Returns a message to print, or None."""
        line = line.strip()
        if not line:
            return None
        command = line.lower()
        if command == "stop":
            self.stop()
            return "stopped"
        if command == "profile":
            return "\n".join(
                "  {:>7g} - {:<7g} Hz  ->  {:20s}  ({})".format(low, high, pattern, feeling)
                for low, high, feeling, pattern in self.profile
            )
        if command == "selftest":
            return self.selftest()
        try:
            freq = float(line)
        except ValueError:
            if line in PATTERN_EFFECTS or line in self.profile_patterns:
                self.trigger(line, now, force=True)
                return "{:20s}  (played by name)".format(line)
            return ("unrecognized {!r}: send a frequency in Hz, a pattern name, "
                    "selftest, profile, or stop".format(line))
        feeling, pattern = classify_frequency(freq, self.profile)
        self.trigger(pattern, now)
        return format_result(freq, feeling, pattern)

    def trigger(self, pattern, now, force=False):
        self.last_input = now
        if force or pattern != self.current_pattern or now - self.last_trigger >= RETRIGGER_SECONDS:
            self.haptics.play(pattern)
            self.current_pattern = pattern
            self.last_trigger = now

    def tick(self, now):
        """Call often from the main loop: stops the motor once the input goes quiet."""
        if self.current_pattern is not None and self.last_input is not None \
                and now - self.last_input > SILENCE_TIMEOUT_SECONDS:
            self.stop()

    def stop(self):
        self.haptics.stop()
        self.current_pattern = None

    def selftest(self):
        """Play each band's pattern once so you can feel the actuator layer against the profile."""
        for low, high, feeling, pattern in self.profile:
            print("  {:>7g} - {:<7g} Hz  {:20s}  should feel: {}".format(low, high, pattern, feeling))
            self.haptics.play(pattern)
            time.sleep(SELFTEST_GAP_SECONDS)
        self.stop()
        return "selftest done"


def read_serial_line(buffer):
    """Non-blocking: move available console bytes into buffer; return a full line or None."""
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch in ("\n", "\r"):
            if buffer:
                line = "".join(buffer)
                del buffer[:]
                return line
        else:
            buffer.append(ch)
    return None


def main():
    print("haptic-audio-calibration / QT Py + DRV2605L")
    try:
        profile = load_profile()
    except OSError:
        print("{} not found. Copy calibration_profile.json from the repo root onto CIRCUITPY.".format(PROFILE_PATH))
        raise
    except (KeyError, TypeError, ValueError):
        print("{} is malformed. Check it on the laptop with validate_calibration.py.".format(PROFILE_PATH))
        raise
    print("Loaded {} with {} bands:".format(PROFILE_PATH, len(profile)))
    for low, high, feeling, pattern in profile:
        print("  {:>7g} - {:<7g} Hz  ->  {:20s}  ({})".format(low, high, pattern, feeling))

    controller = Controller(profile, Haptics())
    print("Ready. Send a frequency in Hz per line (e.g. 440), a pattern name, selftest, profile, or stop.")

    buffer = []
    while True:
        now = time.monotonic()
        line = read_serial_line(buffer)
        if line is not None:
            message = controller.handle_line(line, now)
            if message:
                print(message)
        controller.tick(now)
        time.sleep(0.005)


if __name__ == "__main__":
    main()
