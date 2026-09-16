"""
Phase 1 prototype: Audio -> FFT -> your calibration profile -> printed haptic command

Run this, play some music near your mic (or talk, or hum), and watch the terminal
print which frequency is dominant right now and what haptic pattern your calibration
profile assigns to it. This is the whole pipeline's logic, before any hardware exists.
"""

import numpy as np
import sounddevice as sd

# ---- audio capture settings ----
SAMPLE_RATE = 44100   # samples per second (CD quality)
BLOCK_SIZE = 1024      # samples analyzed per chunk (~23 milliseconds of audio)

# ---- your calibration profile ----
# Replace these with what YOU actually wrote down in your Phase 0 self-test.
# Each entry: (low_hz, high_hz, what it feels like to you, haptic pattern name)
CALIBRATION_PROFILE = [
    (20,    200,   "rough, gravelly, in your gut",     "STRONG_SLOW_PULSE"),
    (200,   500,   "smooth, rounded",                   "STEADY_MEDIUM_VIBE"),
    (500,   2000,  "sharp, bright, pointed",             "SHORT_SHARP_TAP"),
    (2000,  8000,  "thin, glassy, high in the chest",    "FAST_LIGHT_FLUTTER"),
    (8000,  20000, "not yet mapped",                     "UNMAPPED_HIGH"),
]


def classify_frequency(freq_hz):
    """Given a dominant frequency, return (what it feels like, haptic pattern name)."""
    for low, high, feeling, pattern in CALIBRATION_PROFILE:
        if low <= freq_hz < high:
            return feeling, pattern
    return "unknown", "NONE"


def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)

    # indata is a (BLOCK_SIZE, channels) array of raw waveform samples.
    # We just use channel 0 (mono).
    samples = indata[:, 0]

    # ---- FFT: turn this chunk of waveform into a frequency breakdown ----
    fft_result = np.fft.rfft(samples)
    magnitudes = np.abs(fft_result)
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / SAMPLE_RATE)

    # find which frequency has the most energy in this chunk
    dominant_index = np.argmax(magnitudes)
    dominant_freq = freqs[dominant_index]

    # ---- look up what that frequency means to YOU ----
    feeling, pattern = classify_frequency(dominant_freq)

    print(f"{dominant_freq:7.1f} Hz  ->  {pattern:20s}  ({feeling})", flush=True)


print("Listening... play some music or talk near your mic. Ctrl+C to stop.", flush=True)
with sd.InputStream(channels=1, samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, callback=audio_callback):
    sd.sleep(1000 * 60 * 5)  # runs for 5 minutes, or stop earlier with Ctrl+C