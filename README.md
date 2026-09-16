# Haptic Audio Calibration

A synesthesia-calibrated audio-to-haptics pipeline: capture live audio, break it into
its dominant frequency via FFT, and translate that frequency into a haptic pattern
using a personal calibration profile (what each frequency range *feels like* to a
specific person), rather than a generic one-size-fits-all mapping.

## How it works

`haptic_prototype.py` is the Phase 1 prototype — the full pipeline's logic, running
purely in software before any hardware exists:

1. **Capture** — audio is streamed from the microphone in real time (44.1kHz, ~23ms
   blocks).
2. **Analyze** — each block is run through an FFT (`numpy.fft.rfft`) to find the
   dominant frequency present in that chunk.
3. **Calibrate** — the dominant frequency is looked up against a personal
   `CALIBRATION_PROFILE`: frequency ranges mapped to how they subjectively feel
   (e.g. "rough, gravelly, in your gut") and a corresponding haptic pattern name
   (e.g. `STRONG_SLOW_PULSE`).
4. **Output** — the dominant frequency, haptic pattern, and feeling description are
   printed to the terminal live, standing in for what would eventually drive a
   physical haptic actuator.

The calibration profile is meant to be replaced with values from your own Phase 0
self-test — listening to different frequencies and recording what they feel like to
you — rather than using generic defaults.

## Running it

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install numpy sounddevice
python haptic_prototype.py
```

Play music, talk, or hum near your microphone and watch the terminal print the
dominant frequency, its assigned haptic pattern, and its calibrated feeling
description in real time. Stop with Ctrl+C.

## Status

Phase 1: software-only prototype validating the capture → FFT → calibration →
output pipeline before any physical haptic hardware is introduced.
