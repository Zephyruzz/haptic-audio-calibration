# Haptic Audio Calibration

A synesthesia-calibrated audio-to-haptics pipeline. Live audio is broken into frequencies
with an FFT, the dominant frequency is looked up in a **personal calibration profile**
(what each frequency range *feels like* to one specific person, as they themselves
reported it), and the matching haptic pattern drives an actuator.

The distinction the whole project rests on: the profile is not an engineer's mapping of
"bass = rumble, treble = tickle". It is one person's own sound-to-touch association,
elicited from them and recorded verbatim. The engineering around it (FFT, lookup, motor
driver) is deliberately ordinary. See [`INVENTION_DISCLOSURE.md`](INVENTION_DISCLOSURE.md)
for why that distinction matters and how narrow the resulting claim is.

## How it works

```
 microphone ──▶ FFT per ~23 ms block ──▶ dominant frequency
                                               │
                     calibration_profile.json  ▼   [{freq_low, freq_high, feeling, pattern}, ...]
                                               │   half-open bands, first match wins, else NONE
                                               ▼
                                     haptic pattern name ──▶ terminal (Phase 1) / DRV2605L + motor (Phase 2)
```

Two layers are kept apart everywhere in the code:

- **Personal layer**: `calibration_profile.json`, which sound maps to which felt pattern
  for one person. Only that person's Phase 0 self-test can produce it.
- **Actuator layer**: how a given motor renders a named pattern (`PATTERN_EFFECTS` in the
  firmware). Generic, tuned by feel, not the interesting part.

## Current state

| Component | Status | How we know |
|---|---|---|
| `haptic_prototype.py` (Phase 1: mic → FFT → lookup → terminal) | **Built and working** | Confirmed by a live microphone test; `tests/test_pipeline.py` pushes synthetic tones through the same code path and reaches every band. |
| `calibration_profile.json` (the active profile) | **Placeholder data** | It is an engineer's guess, identical to `profiles/placeholder.json`. The prototype and the validator both warn about this at startup. Real data can only come from the inventor running their own Phase 0 self-test, which has not happened. |
| `validate_calibration.py` + `docs/calibration-data-format.md` | **Built and tested** | Schema and cross-field rules covered by `tests/test_validate_calibration.py`; the doc's JSON Schema was cross-checked against the validator. |
| `firmware/qtpy_drv2605/code.py` (Phase 2 board sketch) | **Written, not run on hardware** | Tested under CPython with the CircuitPython modules stubbed (`tests/test_firmware_lookup.py`): same lookup results as the prototype, every placeholder pattern renderable. Never executed on a real QT Py or DRV2605L. |
| `docs/hardware-setup.md` (Phase 2 wiring guide) | **Written** | Parts have not been purchased or wired. |
| Laptop → board serial bridge | **Stub / not written** | The prototype prints to the terminal; the board reads frequencies from its serial console. Connecting them needs a small `pyserial` option on the prototype. Frequencies can be typed into the console meanwhile. |
| Phase 0 self-test tooling | **Not built** | The elicitation procedure is described in `INVENTION_DISCLOSURE.md` §3.2, but there is no software for presenting stimuli and recording answers yet. |
| `INVENTION_DISCLOSURE.md` | **Draft** | Prior art as researched so far, the gap, draft claim concepts, and an honest risk assessment. Needs the inventor's details and a professional review. |

## Phase plan

| Phase | Goal | Status |
|---|---|---|
| **0. Calibrate** | The inventor runs their own self-test: listen to each frequency band, write down what it feels like, pick the matching pattern, repeat later to check stability. Output: a real `calibration_profile.json`. | **Not done.** Nobody but the inventor can do this. |
| **1. Software prototype** | Prove capture → FFT → profile lookup → output in software, no hardware. | **Done.** Live mic test plus automated synthetic test. |
| **2. Hardware** | Buy and wire the solder-free build (QT Py + DRV2605L + ERM disc), run the firmware, feel the patterns; then write the serial bridge and tune the actuator layer. | **Prep code done; hardware not purchased or wired.** |
| **3. Evidence** (proposed) | Test-retest of the inventor's profile, profiles from other people, and an A/B comparison of personal vs generic mapping. This is what a patent filing would need. | **Not started.** |

## Getting started

Fresh machine, nothing installed yet:

```bash
git clone https://github.com/Zephyruzz/haptic-audio-calibration.git
cd haptic-audio-calibration
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # numpy + sounddevice
python -m unittest                # 1. prove the pipeline logic with synthetic tones (no mic needed)
python haptic_prototype.py        # 2. live: Ctrl+C to stop; --profile PATH to try another profile
```

On Linux, `sounddevice` also needs the PortAudio system library
(`sudo apt install libportaudio2` on Debian/Ubuntu). macOS and Windows wheels bundle it.
If the prototype exits with "Could not load the audio backend", that is the missing piece;
the tests still run without it.

Play music, talk, or hum near the microphone and watch the terminal print the dominant
frequency, its haptic pattern, and its calibrated feeling in real time. The first lines
tell you which profile is loaded and warn if it is still the placeholder. When you have
your own profile, see [Swapping in a real profile](#swapping-in-a-real-profile); for the
hardware build, see [`docs/hardware-setup.md`](docs/hardware-setup.md).

## Tests

```bash
python -m unittest
```

Needs only numpy. No microphone, no PortAudio, no hardware. Covers the FFT + lookup
pipeline with synthetic tones, the profile validator, and the firmware's lookup logic
under stubbed CircuitPython modules.

## Swapping in a real profile

```bash
python validate_calibration.py --check-only path/to/my_profile.json   # just check it
python validate_calibration.py path/to/my_profile.json                # check, then make it active
```

The format is defined in [`docs/calibration-data-format.md`](docs/calibration-data-format.md).
The previous active profile is kept as `calibration_profile.backup.json`. A real profile is
personal data and the artifact the project's claim rests on; decide deliberately whether
to commit it.

## Repository layout

```
haptic_prototype.py            Phase 1 prototype (laptop)
calibration_profile.json       ACTIVE profile, loaded at runtime -- currently placeholder data
profiles/placeholder.json      pristine copy of the placeholder, for reset and detection
validate_calibration.py        schema check + swap-in of a profile
firmware/qtpy_drv2605/code.py  Phase 2 CircuitPython sketch (QT Py + DRV2605L)
tests/                         python -m unittest
docs/hardware-setup.md         Phase 2 shopping list and wiring
docs/calibration-data-format.md  the profile JSON format
INVENTION_DISCLOSURE.md        patent angle, prior art, honest risk assessment
STATUS.md                      what this session completed and what only the inventor can do
```

## Known limitations of the prototype

Documented rather than fixed, because the live mic test was done with this exact
behaviour:

- No window function before the FFT, so tones leak into neighbouring bins. Fine for
  finding the loudest bin; not fine for anything subtler.
- The DC bin is included in the argmax, so silence reports 0 Hz, which maps to `NONE`.
- One dominant frequency per 23 ms block. Chords, noise, and speech collapse to whichever
  bin happens to win. Frequency resolution is about 43 Hz, so bands narrower than that
  cannot be resolved and tones near a band edge can land in the neighbouring band.
- Loudness is ignored entirely; the profile has no intensity dimension yet.
