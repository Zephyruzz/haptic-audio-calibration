# Calibration profile format

A calibration profile is the record of what sound feels like to **one specific person**:
for each range of audio frequencies, the tactile quality that person reports it evokes,
and the name of the haptic pattern that matches. It is the personal, synesthetic layer of
this project. Everything else (FFT, lookup, motor driving) is ordinary engineering that
exists to deliver this file to the skin.

This document is the contract for that file. It is what a Phase 0 self-test must produce,
what `haptic_prototype.py` and the firmware load, and what `validate_calibration.py`
checks. It defines the format only. Nothing about the format can tell a genuine
synesthetic association from a made-up one; that comes from how the data was collected.

## Files

| Path | Role |
|---|---|
| `calibration_profile.json` | The **active** profile. Loaded by `haptic_prototype.py` at startup and copied onto the `CIRCUITPY` drive for the firmware. Tracked in git, and shipped as a copy of the placeholder. |
| `profiles/placeholder.json` | The placeholder data that used to be hardcoded in the script: an engineer's guess, not a measurement. Kept pristine so the tools can recognise when the active profile is still the placeholder. |
| `calibration_profile.backup.json` | Written by `validate_calibration.py` when it swaps a new profile in; the previous active profile. Ignored by git. |

Encoding is UTF-8. Formatting (indentation, key order) is free; the tools copy your file
byte-for-byte rather than rewriting it.

## Shape

The file is a **JSON array** of band objects. Each object has exactly these four keys:

| Key | Type | Meaning |
|---|---|---|
| `freq_low` | number (Hz) | Lower edge of the band, **inclusive**. `>= 0`. |
| `freq_high` | number (Hz) | Upper edge of the band, **exclusive**. Must be greater than `freq_low`. |
| `feeling` | string | What sound in this band feels like to this person, in their own words, exactly as they reported it. Free text, non-empty. This is the synesthetic report; keep it verbatim, don't tidy it into engineering language. |
| `pattern` | string | The name of the haptic pattern that best matches the feeling. An `UPPER_SNAKE_CASE` identifier (`^[A-Z][A-Z0-9_]*$`), e.g. `SHORT_SHARP_TAP`. This is the handle the actuator layer renders (see `PATTERN_EFFECTS` in the firmware). `NONE` is reserved. |

This is exactly the shape the original hardcoded `CALIBRATION_PROFILE` had, with the
tuple positions given names.

### Example: the placeholder

```json
[
  { "freq_low": 20,   "freq_high": 200,   "feeling": "rough, gravelly, in your gut",  "pattern": "STRONG_SLOW_PULSE" },
  { "freq_low": 200,  "freq_high": 500,   "feeling": "smooth, rounded",                "pattern": "STEADY_MEDIUM_VIBE" },
  { "freq_low": 500,  "freq_high": 2000,  "feeling": "sharp, bright, pointed",         "pattern": "SHORT_SHARP_TAP" },
  { "freq_low": 2000, "freq_high": 8000,  "feeling": "thin, glassy, high in the chest", "pattern": "FAST_LIGHT_FLUTTER" },
  { "freq_low": 8000, "freq_high": 20000, "feeling": "not yet mapped",                  "pattern": "UNMAPPED_HIGH" }
]
```

A real profile does not have to look like this. It may have two bands or twenty, bands of
very different widths, the same pattern in non-adjacent bands, and feelings that are
sentences rather than adjectives. Those are findings, not mistakes.

## How the profile is interpreted

The lookup rule is identical in `haptic_prototype.classify_frequency` and in the firmware:

1. Bands are half-open intervals: a frequency `f` matches a band when
   `freq_low <= f < freq_high`. So `200` belongs to the `200–500` band, not the `20–200` one.
2. Bands are checked in file order and the **first match wins**.
3. A frequency that matches no band yields the pattern `NONE` (and the feeling `unknown`),
   which the actuator layer renders as silence.

Because of rule 2, overlapping bands would make the result depend on file order, which is
why overlaps are rejected (below). Gaps are allowed: a person who has not mapped a range
simply gets `NONE` there, which is more honest than inventing a pattern.

## Formal schema

JSON Schema (draft 2020-12). The structural rules live here; the cross-field rules that
JSON Schema cannot express follow in the next section.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Haptic audio calibration profile",
  "description": "One person's mapping from audio frequency bands to felt haptic patterns, as reported in their own Phase 0 self-test.",
  "type": "array",
  "minItems": 1,
  "items": {
    "type": "object",
    "required": ["freq_low", "freq_high", "feeling", "pattern"],
    "additionalProperties": false,
    "properties": {
      "freq_low": {
        "type": "number",
        "minimum": 0,
        "description": "Lower edge of the band in Hz, inclusive."
      },
      "freq_high": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": "Upper edge of the band in Hz, exclusive. Must be greater than freq_low."
      },
      "feeling": {
        "type": "string",
        "minLength": 1,
        "description": "What sound in this band feels like to this person, in their own words, verbatim."
      },
      "pattern": {
        "type": "string",
        "pattern": "^[A-Z][A-Z0-9_]*$",
        "not": { "const": "NONE" },
        "description": "UPPER_SNAKE_CASE name of the haptic pattern matching the feeling. NONE is reserved for 'no band matched'."
      }
    }
  }
}
```

## Rules beyond the schema

`validate_calibration.py` enforces the schema above and these cross-field rules. Errors
make a profile invalid; warnings are printed but do not block activation.

| Rule | Level | Why |
|---|---|---|
| `freq_low < freq_high` in every band | error | A band must have positive width. |
| Both frequencies finite (no `NaN`, no `Infinity`) and not booleans | error | Python's JSON parser accepts `NaN`; the lookup would never match it. |
| `feeling` is not blank after trimming whitespace | error | The report is the point of the file. |
| `pattern` is not `NONE` | error | `NONE` is what the lookup returns when nothing matched. |
| No two bands overlap | error | One frequency must map to one pattern regardless of file order. |
| Bands listed in ascending frequency order | warning | Allowed by the lookup rule; unsorted files are just harder to read and compare. |
| Gaps between bands | warning | Legitimate ("I haven't mapped that range"), but you should know where they are. |
| Any edge above 22 050 Hz | warning | The Phase 1 prototype samples at 44.1 kHz and can never report a frequency above half that. |
| Profile identical to `profiles/placeholder.json` | warning | You are activating the placeholder, not your own data. |

Repeated pattern names across bands are **allowed** and are not even warned about. If
100 Hz and 6 kHz both feel like the same thing to someone, the file should say so.

## Using a profile

```bash
# Check a file without changing anything
python validate_calibration.py --check-only path/to/my_profile.json

# Check it and, if valid, make it the active profile (the previous one is kept as
# calibration_profile.backup.json)
python validate_calibration.py path/to/my_profile.json

# Run the prototype with it
python haptic_prototype.py

# Or try a profile once without activating it
python haptic_prototype.py --profile path/to/my_profile.json
```

For the hardware build, copy the activated `calibration_profile.json` onto the `CIRCUITPY`
drive (see `docs/hardware-setup.md`), and make sure every `pattern` name in it has an
entry in the firmware's `PATTERN_EFFECTS` table, otherwise that band is silent.

## Provenance, privacy, and what the file deliberately leaves out

The file carries no metadata: no name, date, or description of how it was collected. That
is a deliberate consequence of keeping the shape identical to the original
`CALIBRATION_PROFILE`, and a bare JSON array has nowhere to put such fields without
changing the shape. But provenance is what makes a profile evidence rather than a list
of numbers, so record it next to the file: for example `profiles/<name>.notes.md` with
whose profile it is, the date, the stimulus used for each band (pure tone, band-limited
noise, music excerpt), the playback level and device, and whether the person has repeated
the test and got the same answers. Test-retest stability is the single strongest thing
you can show about a profile.

A real profile is personal data about one person's perception, and it is the artifact
the whole project's claim rests on. `calibration_profile.json` is tracked by git, so
swapping your own profile in will show up as a modification. Decide deliberately whether
to commit it, and if the repository is public, whether you want it public at all before
anything is filed.

## Versioning

This is version 1 of the format. Changes that would break it (a metadata wrapper,
per-band intensity, multiple stimuli per band) should turn the top level into an object
such as `{"schema_version": 2, "bands": [...]}` so that loaders can distinguish the two;
loaders should then keep accepting the bare-array form as version 1.
