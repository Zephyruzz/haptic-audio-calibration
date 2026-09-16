"""
Phase 1 prototype: Audio -> FFT -> your calibration profile -> printed haptic command

Run this, play some music near your mic (or talk, or hum), and watch the terminal
print which frequency is dominant right now and what haptic pattern your calibration
profile assigns to it. This is the whole pipeline's logic, before any hardware exists.

The calibration profile is loaded at runtime from calibration_profile.json (format:
docs/calibration-data-format.md). The copy that ships in this repo is PLACEHOLDER
data -- an engineer's guess at what each frequency range might feel like. It is not a
measured synesthetic association, and the personalized association is the entire point
of this project. Replace it with what YOU actually wrote down in your Phase 0 self-test:

    python validate_calibration.py path/to/your_profile.json

The FFT and lookup steps are plain functions (dominant_frequency, classify_frequency,
process_block) so they can be exercised without a microphone -- see
tests/test_pipeline.py. sounddevice is imported only when the live mic stream starts,
so importing this module never needs PortAudio.
"""

import argparse
import json
import os
import sys

import numpy as np

# ---- audio capture settings ----
SAMPLE_RATE = 44100   # samples per second (CD quality)
BLOCK_SIZE = 1024      # samples analyzed per chunk (~23 milliseconds of audio)

# ---- your calibration profile ----
# Lives in calibration_profile.json, one object per frequency band:
#   {"freq_low": Hz, "freq_high": Hz, "feeling": what it feels like to you, "pattern": haptic pattern name}
# load_calibration_profile() turns those into the same (low_hz, high_hz, feeling, pattern)
# tuples this file used when the profile was hardcoded here.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE_PATH = os.path.join(REPO_ROOT, "calibration_profile.json")
PLACEHOLDER_PROFILE_PATH = os.path.join(REPO_ROOT, "profiles", "placeholder.json")

REQUIRED_KEYS = ("freq_low", "freq_high", "feeling", "pattern")


def load_calibration_profile(path=DEFAULT_PROFILE_PATH):
    """Load a calibration profile JSON file.

    Returns a list of (low_hz, high_hz, feeling, pattern) tuples. Only the basic
    structure is checked here; validate_calibration.py does the full schema check.
    """
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        raise ValueError(
            f"{path}: expected a JSON array of calibration entries "
            "(see docs/calibration-data-format.md; check the file with validate_calibration.py)"
        )
    profile = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or any(key not in entry for key in REQUIRED_KEYS):
            raise ValueError(
                f"{path}: entry {index} must be an object with keys {', '.join(REQUIRED_KEYS)} "
                "(see docs/calibration-data-format.md; check the file with validate_calibration.py)"
            )
        profile.append((entry["freq_low"], entry["freq_high"], entry["feeling"], entry["pattern"]))
    return profile


def is_placeholder_profile(profile):
    """True if this profile is identical to the repo's placeholder data -- i.e. NOT your own."""
    try:
        return profile == load_calibration_profile(PLACEHOLDER_PROFILE_PATH)
    except (OSError, ValueError):
        return False


def classify_frequency(freq_hz, profile):
    """Given a dominant frequency, return (what it feels like, haptic pattern name).

    Bands are half-open: an entry matches when freq_low <= freq_hz < freq_high, and the
    first matching entry wins. A frequency outside every band is ("unknown", "NONE").
    """
    for low, high, feeling, pattern in profile:
        if low <= freq_hz < high:
            return feeling, pattern
    return "unknown", "NONE"


def dominant_frequency(samples, sample_rate=SAMPLE_RATE):
    """FFT one block of mono samples and return the frequency (Hz) with the most energy."""
    fft_result = np.fft.rfft(samples)
    magnitudes = np.abs(fft_result)
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
    dominant_index = np.argmax(magnitudes)
    return float(freqs[dominant_index])


def process_block(indata, profile, sample_rate=SAMPLE_RATE):
    """Run one audio block through the whole pipeline: FFT -> dominant frequency -> lookup.

    indata is a (frames, channels) array of raw waveform samples, exactly what
    sounddevice hands to the stream callback. Returns (dominant_hz, feeling, pattern).
    """
    samples = indata[:, 0]   # channel 0 (mono)
    freq = dominant_frequency(samples, sample_rate)
    feeling, pattern = classify_frequency(freq, profile)
    return freq, feeling, pattern


def format_result(freq, feeling, pattern):
    """One terminal line, e.g. '  440.0 Hz  ->  SHORT_SHARP_TAP       (sharp, bright, pointed)'."""
    return f"{freq:7.1f} Hz  ->  {pattern:20s}  ({feeling})"


def make_audio_callback(profile):
    """Build the sounddevice stream callback for a given profile."""
    def audio_callback(indata, frames, time_info, status):
        if status:
            print(status)
        freq, feeling, pattern = process_block(indata, profile)
        print(format_result(freq, feeling, pattern), flush=True)
    return audio_callback


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Listen on the microphone and print the haptic pattern your calibration "
                    "profile assigns to the dominant frequency of each ~23 ms block."
    )
    parser.add_argument(
        "--profile", default=DEFAULT_PROFILE_PATH,
        help="calibration profile JSON to use (default: calibration_profile.json next to this script)",
    )
    parser.add_argument(
        "--seconds", type=float, default=5 * 60,
        help="how long to listen before exiting (default: 5 minutes; Ctrl+C stops earlier)",
    )
    args = parser.parse_args(argv)

    profile = load_calibration_profile(args.profile)
    print(f"Calibration profile: {args.profile}  ({len(profile)} frequency bands)")
    if is_placeholder_profile(profile):
        print("WARNING: this is the PLACEHOLDER profile, not your own synesthetic data.\n"
              "         Run your Phase 0 self-test, then swap your profile in with validate_calibration.py.")
    for low, high, feeling, pattern in profile:
        print(f"  {low:>7g} - {high:<7g} Hz  ->  {pattern:20s}  ({feeling})")

    try:
        # Imported here, not at module top, so the FFT + lookup logic above can be tested
        # on a machine with no microphone and no PortAudio.
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        sys.exit(
            f"Could not load the audio backend: {exc}\n"
            "Install the requirements (pip install -r requirements.txt) and, on Linux, the PortAudio\n"
            "library (e.g. sudo apt install libportaudio2). To exercise the pipeline without a mic,\n"
            "run the synthetic test instead:  python -m unittest"
        )

    print("Listening... play some music or talk near your mic. Ctrl+C to stop.", flush=True)
    try:
        with sd.InputStream(channels=1, samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                            callback=make_audio_callback(profile)):
            sd.sleep(int(args.seconds * 1000))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
