#!/usr/bin/env python3
"""
Check a calibration profile against docs/calibration-data-format.md and, if it passes,
make it the active profile that haptic_prototype.py and the firmware load
(calibration_profile.json).

    python validate_calibration.py my_profile.json                # validate, then activate
    python validate_calibration.py --check-only my_profile.json   # validate only
    python validate_calibration.py                                # re-check the active profile

Standard library only: runs anywhere Python does, no numpy or microphone needed.
Exit status 0 = valid, 1 = invalid, 2 = could not read the file.

What this tool cannot do: a profile is a record of what sound feels like to ONE specific
person. This checks the file's shape, not its truth. Nothing here can tell a genuine
synesthetic association from a made-up one; only the way the data was collected can.
"""

import argparse
import json
import math
import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ACTIVE_PROFILE_PATH = os.path.join(REPO_ROOT, "calibration_profile.json")
PLACEHOLDER_PROFILE_PATH = os.path.join(REPO_ROOT, "profiles", "placeholder.json")

REQUIRED_KEYS = ("freq_low", "freq_high", "feeling", "pattern")
PATTERN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
RESERVED_PATTERNS = {"NONE"}      # what classify_frequency returns when no band matches
NYQUIST_HZ = 44100 / 2            # the highest frequency the Phase 1 prototype can report


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_profile(data, placeholder_path=PLACEHOLDER_PROFILE_PATH):
    """Validate a parsed JSON document. Returns (errors, warnings), two lists of strings.

    Errors mean the file violates the format. Warnings are things worth a look that do
    not block activation.
    """
    errors, warnings = [], []
    if not isinstance(data, list):
        return [f"top level must be a JSON array of band objects, got {type(data).__name__}"], warnings
    if not data:
        return ["profile has no bands (empty array)"], warnings

    bands = []   # (index, low, high) for entries whose frequencies are usable
    for i, entry in enumerate(data):
        where = f"entry {i}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object with keys {', '.join(REQUIRED_KEYS)}")
            continue
        missing = [key for key in REQUIRED_KEYS if key not in entry]
        extra = [key for key in entry if key not in REQUIRED_KEYS]
        if missing:
            errors.append(f"{where}: missing key(s) {', '.join(missing)}")
        if extra:
            errors.append(f"{where}: unexpected key(s) {', '.join(extra)} "
                          f"(only {', '.join(REQUIRED_KEYS)} are allowed)")

        freqs_ok = True
        for name in ("freq_low", "freq_high"):
            if name not in entry:
                freqs_ok = False
            elif not _is_number(entry[name]):
                errors.append(f"{where}: {name} must be a finite number in Hz, got {entry[name]!r}")
                freqs_ok = False
            elif entry[name] < 0:
                errors.append(f"{where}: {name} must not be negative, got {entry[name]!r}")
                freqs_ok = False
        if freqs_ok:
            low, high = entry["freq_low"], entry["freq_high"]
            if not low < high:
                errors.append(f"{where}: freq_low ({low!r}) must be less than freq_high ({high!r})")
            else:
                bands.append((i, low, high))
                if high > NYQUIST_HZ:
                    warnings.append(f"{where}: freq_high {high!r} Hz is above what the prototype can "
                                    f"measure ({NYQUIST_HZ:g} Hz at a 44.1 kHz sample rate)")

        if "feeling" in entry:
            feeling = entry["feeling"]
            if not isinstance(feeling, str) or not feeling.strip():
                errors.append(f"{where}: feeling must be a non-empty string "
                              "(the person's own words for what this band feels like)")

        if "pattern" in entry:
            pattern = entry["pattern"]
            if not isinstance(pattern, str) or not PATTERN_RE.match(pattern):
                errors.append(f"{where}: pattern must be an UPPER_SNAKE_CASE name like "
                              f"SHORT_SHARP_TAP, got {pattern!r}")
            elif pattern in RESERVED_PATTERNS:
                errors.append(f"{where}: pattern {pattern} is reserved for 'no band matched'")

    # Cross-band rules: overlap is an error, gaps and unsorted order are warnings.
    bands_sorted = sorted(bands, key=lambda band: (band[1], band[2]))
    if [band[0] for band in bands_sorted] != [band[0] for band in bands]:
        warnings.append("bands are not in ascending frequency order (allowed, but harder to read)")
    reach_index, reach_high = None, None
    for index, low, high in bands_sorted:
        if reach_high is not None:
            if low < reach_high:
                errors.append(f"entries {reach_index} and {index} overlap ({low!r} Hz is inside both); "
                              "one frequency must map to exactly one pattern")
            elif low > reach_high:
                warnings.append(f"gap between entries {reach_index} and {index}: "
                                f"{reach_high!r}-{low!r} Hz will map to NONE")
        if reach_high is None or high > reach_high:
            reach_index, reach_high = index, high

    if not errors:
        try:
            with open(placeholder_path, encoding="utf-8") as f:
                if data == json.load(f):
                    warnings.append("this is the repo's PLACEHOLDER profile, not a measured "
                                    "synesthetic profile; the real data can only come from your "
                                    "own Phase 0 self-test")
        except (OSError, ValueError):
            pass
    return errors, warnings


def activate(source_path, active_path=ACTIVE_PROFILE_PATH):
    """Copy source over the active profile, keeping the previous active profile as a backup.

    Returns a list of messages describing what happened. The source file is copied
    byte-for-byte and left where it is.
    """
    source_abs = os.path.abspath(source_path)
    active_abs = os.path.abspath(active_path)
    if source_abs == active_abs:
        return [f"{source_path} is already the active profile; nothing to swap"]
    messages = []
    if os.path.exists(active_abs):
        backup_path = os.path.splitext(active_abs)[0] + ".backup.json"
        shutil.copyfile(active_abs, backup_path)
        messages.append(f"previous active profile saved as {backup_path}")
    shutil.copyfile(source_abs, active_abs)
    messages.append(f"{source_path} is now the active profile: {active_abs}")
    return messages


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate a calibration profile against docs/calibration-data-format.md and, "
                    "if it is valid, make it the active profile (calibration_profile.json).",
    )
    parser.add_argument("profile", nargs="?",
                        help="profile JSON to check; omit to re-check the active profile (check only)")
    parser.add_argument("--check-only", action="store_true",
                        help="validate without making it the active profile")
    parser.add_argument("--active", default=ACTIVE_PROFILE_PATH, metavar="PATH",
                        help="where the active profile lives (default: calibration_profile.json in the repo)")
    args = parser.parse_args(argv)

    path = args.profile or args.active
    check_only = args.check_only or args.profile is None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return 2
    except ValueError as exc:
        print(f"INVALID: {path} is not valid JSON: {exc}")
        return 1

    errors, warnings = validate_profile(data)
    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        print(f"INVALID: {path} has {len(errors)} problem(s):")
        for error in errors:
            print(f"  - {error}")
        print("Format reference: docs/calibration-data-format.md")
        return 1

    print(f"OK: {path} is a valid calibration profile ({len(data)} bands)")
    if check_only:
        return 0

    for message in activate(path, args.active):
        print(message)
    print("Next: python haptic_prototype.py   (and copy the new calibration_profile.json onto CIRCUITPY\n"
          "      for the firmware; make sure its PATTERN_EFFECTS table renders every pattern name).\n"
          "Note: calibration_profile.json is tracked by git and a real profile is personal data --\n"
          "      decide deliberately whether to commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
