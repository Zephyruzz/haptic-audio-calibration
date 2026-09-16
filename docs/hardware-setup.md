# Hardware setup: the solder-free Phase 2 build

Phase 1 proved the pipeline in software: microphone → FFT → *your* calibration profile →
a haptic pattern name printed to the terminal. Phase 2 puts a real motor on the end of
that pipeline. This guide is the shopping list and wiring for the smallest build that
does that, using plug-together STEMMA QT parts.

The reference implementation for the board is **[`firmware/qtpy_drv2605/code.py`](../firmware/qtpy_drv2605/code.py)**.
It reads the same `calibration_profile.json` the laptop prototype uses, applies the same
lookup rule, and drives a DRV2605L haptic controller. Nothing in it assumes hardware is
present: with no driver attached it runs in dry-run mode and prints what it would play.

Two things this guide does **not** do:

- It does not calibrate anything. The profile that decides which sound feels like which
  pattern comes only from your own Phase 0 self-test. The firmware just carries that
  profile onto a device. The repo ships placeholder data, and the board will happily play
  the placeholder; that proves the hardware, not the idea.
- It does not put a microphone on the board. For a first build the laptop keeps doing
  capture and FFT and sends the dominant frequency to the board over USB serial. See
  [Feeding it real audio](#feeding-it-real-audio).

## Read this first: how solder-free is it?

Everything between the microcontroller and the haptic driver is plug-together: one STEMMA
QT cable carries power, ground, and I2C. The one exception is the motor itself.

The DRV2605L breakout brings the motor out on **two solder pads labelled Motor+ and
Motor-**, not a connector, and the vibrating mini motor disc has two bare wire leads. So
"solder-free" honestly means "solder-free except for two joints". Your options:

1. **Make the two joints.** Anyone with a soldering iron can do this in a couple of
   minutes: tin the two leads, poke each through its pad hole, solder. If you don't own an
   iron, a makerspace, a school lab, or a friend who solders is the fastest route. This is
   the recommended option; it is also the only reliable one.
2. **Zero-solder workaround for a first buzz.** Strip a few millimetres more of each lead,
   thread it through the pad hole, wrap the bare wire around the pad two or three turns,
   pinch it flat with pliers, and hold it down with a dab of hot glue or a strip of tape.
   It is enough to feel every effect and tune the actuator layer. Expect dropouts when the
   wire moves, and don't trust it for anything you want to demonstrate.
3. **A different board with the motor already on it.** SparkFun's Qwiic Haptic Driver
   (DA7280) has a tiny LRA soldered on the board, so it is genuinely zero-solder. It is a
   different chip with a different library (Arduino support exists; CircuitPython support
   is not confirmed), and the motor is an LRA, which is exactly what this first build is
   trying to avoid. Keep it in mind for later; skip it now.

## Parts

Prices are approximate US list prices at the time of writing; check the product pages.

| Part | Adafruit product | ~Price | Notes |
|---|---|---|---|
| Adafruit QT Py RP2040 | 4900 | $10 | The recommended brain: USB-C, STEMMA QT port, 264 KB RAM (plenty for CircuitPython + JSON). Any STEMMA QT board that runs CircuitPython works, e.g. QT Py SAMD21 (cheaper, tight on RAM) or QT Py ESP32-S3. |
| Adafruit DRV2605L Haptic Motor Controller, STEMMA QT / Qwiic | 2305 | $8 | The haptic driver. Two STEMMA QT ports (chainable), I2C address 0x5A, drives ERM and LRA motors. Motor attaches to the Motor+ / Motor- pads. Ships with a strip of header you don't need. |
| STEMMA QT / Qwiic JST SH 4-pin cable, 100 mm | 4210 | $1 | Any length works; 50 mm and 200 mm versions exist too. |
| Vibrating Mini Motor Disc | 1201 | $2 | ERM coin motor, 10 mm diameter, 2.7 mm thick, rated 2–5 V (about 60 mA at 3 V), two bare leads (red, blue). Start here; see [ERM now, LRA later](#erm-now-lra-later). |
| USB-C cable that carries data | — | — | Many bundled cables are charge-only. If the board never shows up as a drive, try another cable. |

Total: about $21 plus the cable. Optional extras: double-sided foam tape to stick the
motor to something (a wristband, the back of your hand), a cheap soldering iron if you
choose option 1 above.

## How the pieces connect

```
 laptop ──USB-C──▶ QT Py RP2040 ──STEMMA QT cable──▶ DRV2605L breakout ──Motor+ / Motor- pads──▶ motor disc
                    (3.3 V, GND,                       (3.3 V, GND,                                 (red, blue leads)
                     SDA1, SCL1)                        SDA, SCL)
```

1. **QT Py → DRV2605L.** Plug the STEMMA QT cable into the QT Py's STEMMA QT port and into
   either of the two ports on the DRV2605L. The connectors are keyed; they only go in one
   way. The cable carries 3.3 V, GND, SDA and SCL, so the driver is powered and wired in
   one step. On the QT Py RP2040 the STEMMA QT port is its **own** I2C bus (pins SDA1/SCL1,
   GPIO22/GPIO23), separate from the SDA/SCL castellated pins. The sketch asks for it with
   `board.STEMMA_I2C()` and falls back to `board.I2C()` on boards where the port shares the
   main SDA/SCL pins, so you don't have to care which board you bought.
2. **DRV2605L → motor.** Red lead to **Motor+**, blue lead to **Motor-**, using one of the
   options in the section above. For an ERM disc, polarity only changes the spin
   direction; it buzzes either way.
3. **Power.** Everything runs from the laptop's USB port through the QT Py. The driver
   gets 3.3 V over the STEMMA QT cable and drives the motor from that supply, which is
   inside the disc's 2–5 V rating. Effects will feel a little softer than the motor's
   5 V figures; that is fine for a first build.

Nothing else is connected. No breadboard, no jumper wires, no external power.

## Put CircuitPython and the sketch on the board

1. **Install CircuitPython** (skip if the board already shows up as a `CIRCUITPY` drive).
   For the QT Py RP2040: hold the **BOOT** button while plugging in USB (or hold BOOT and
   tap RESET). A drive named `RPI-RP2` appears. Download the CircuitPython `.uf2` for the
   Adafruit QT Py RP2040 from circuitpython.org (use the current stable release) and drag
   it onto `RPI-RP2`. The board reboots and reappears as `CIRCUITPY`. Other boards use the
   same drag-a-`.uf2` flow with a different bootloader button sequence; follow the board's
   own CircuitPython page.
2. **Install the driver library.** Download the CircuitPython Library Bundle that matches
   your CircuitPython major version, and copy these into `CIRCUITPY/lib/`:
   - `adafruit_drv2605.mpy`
   - the `adafruit_bus_device/` folder (the only dependency `adafruit_drv2605` has)

   Or, with `circup` installed on the laptop: `circup install adafruit_drv2605`.
3. **Copy the sketch and the profile.** From this repo:
   - `firmware/qtpy_drv2605/code.py` → `CIRCUITPY/code.py`
   - `calibration_profile.json` → `CIRCUITPY/calibration_profile.json`

   The board runs `code.py` automatically whenever it is saved or the board resets. If you
   later swap in your real profile with `validate_calibration.py`, copy the new
   `calibration_profile.json` over again.
4. **Open the serial console.** Any serial terminal works; the USB baud rate setting is
   ignored. Mu and Thonny have a built-in console. From a shell:
   `screen /dev/tty.usbmodem* 115200` (macOS), `tio /dev/ttyACM0` (Linux), or PuTTY on the
   COM port (Windows). Ctrl+C in the console stops `code.py` and drops to the REPL; Ctrl+D
   restarts it.

## First power-up

You should see something like:

```
haptic-audio-calibration / QT Py + DRV2605L
Loaded /calibration_profile.json with 5 bands:
       20 - 200     Hz  ->  STRONG_SLOW_PULSE     (rough, gravelly, in your gut)
      200 - 500     Hz  ->  STEADY_MEDIUM_VIBE    (smooth, rounded)
      ...
DRV2605L found; motor type ERM
Ready. Send a frequency in Hz per line (e.g. 440), a pattern name, selftest, profile, or stop.
```

If instead you see `DRY RUN`, the board could not find the driver or its library; the
sketch keeps running and prints what it would have played. See
[Troubleshooting](#troubleshooting).

Now type commands into the console, one per line:

| You type | What happens |
|---|---|
| `selftest` | Plays every band's pattern once, in profile order, printing the band and its `feeling` text. Hold the motor while it runs. |
| `100`, `350`, `1000`, `5000` | Classifies that frequency with the profile and plays the resulting pattern, printing the same line the laptop prototype prints. |
| `SHORT_SHARP_TAP` | Plays a pattern by name, bypassing the profile, so you can judge the motor's rendering on its own. |
| `profile` | Prints the loaded profile. |
| `stop` | Stops the motor. |

While frequencies in the same band keep arriving, the pattern is re-triggered about every
0.35 s (the DRV2605L's library effects are one-shots). Half a second of silence on the
wire stops the motor. Both constants are at the top of the sketch.

## Feeding it real audio

**Current state: the laptop → board serial bridge is not written yet.** The prototype
prints its results to the terminal; the board reads frequencies from its serial console.
The next code step for Phase 2 is a small option on `haptic_prototype.py` that writes
each block's dominant frequency to the board's serial port (with `pyserial`). Until then:

- Typing frequencies into the console, as above, exercises the whole board-side pipeline.
- On Linux or macOS you can pipe the prototype's output straight to the board's port,
  because each output line begins with the frequency. Something like
  `python -u haptic_prototype.py | cut -c1-8 > /dev/ttyACM0` (with the serial console
  closed, and after `stty -F /dev/ttyACM0 raw` if the port mangles line endings). The
  banner lines will arrive as garbage and be answered with `unrecognized ...`, which is
  harmless. This shortcut is untested here and is a stopgap, not the design.

## Tuning the actuator layer

The sketch has two tables and it matters which one you are editing.

- `calibration_profile.json` is the **personal** layer: which frequency band produces
  which felt pattern for one specific person. It is only ever changed by that person's
  Phase 0 self-test, via `validate_calibration.py` on the laptop.
- `PATTERN_EFFECTS` in `code.py` is the **actuator** layer: how *this motor on this
  driver* renders a pattern name, as DRV2605L waveform-library effect IDs (1–123, up to
  8 per sequence). The shipped values are first guesses for the placeholder pattern names.

To tune the actuator layer, play patterns by name from the console, decide whether
`SHORT_SHARP_TAP` actually feels short and sharp on your motor, and edit the effect IDs.
The full effect list is in the TI DRV2605L datasheet ("Waveform Library Effects List");
the shipped guesses are 52 Pulsing Strong, 48 Buzz 2, 4 Sharp Click, 57 Pulsing Sharp 2.
When your real profile introduces new pattern names, add an entry for each one; the
sketch warns at startup about any name it cannot render.

Getting the rendering right is worth doing, but it is not the calibration. A perfectly
rendered `SHORT_SHARP_TAP` attached to the wrong frequency band is still a generic
engineer's mapping.

## ERM now, LRA later

Start with the ERM disc. It is an ordinary DC motor with an off-centre weight: apply
voltage, it vibrates, done. The DRV2605L drives it open-loop with its ERM effect library
(libraries 1–5), which is what the sketch selects.

Linear resonant actuators (LRAs) feel crisper and respond faster, which will matter for
distinguishing patterns later. But an LRA only moves well at its own resonant frequency
(typically somewhere around 170–235 Hz depending on the part), and the DRV2605L has to be
told about the motor (rated voltage, overdrive clamp) and then run its auto-calibration
routine (`MODE_AUTOCAL`) to lock onto that resonance. Get the wrong parameters and you get
a faint hum or nothing. That is a second project. When you are ready: set `MOTOR_TYPE =
"LRA"` in the sketch (which switches the driver to `use_LRM()` and the LRA effect
library 6), read the DRV2605L datasheet's LRA auto-calibration section, and pick an LRA
whose resonant frequency is stated on its datasheet.

One more thing worth knowing: the DRV2605L has an **audio-to-vibe** mode
(`MODE_AUDIOVIBE`) that turns an analog audio input directly into vibration with no
software at all. It is the textbook generic audio→haptic path, the same for every user.
This project is deliberately not that, which is why the audio goes through the FFT and the
personal profile in software instead.

## Troubleshooting

| Symptom | Things to check |
|---|---|
| No `CIRCUITPY` drive | Charge-only USB cable; bootloader step skipped; wrong `.uf2` for the board. |
| Console says `DRY RUN ... adafruit_drv2605 is not in /lib` | Library not copied, or copied for the wrong CircuitPython major version (mismatched `.mpy` files fail to import). |
| Console says `DRY RUN ... No DRV2605L answered on I2C` | Cable not fully seated at one end; wrong port on the QT Py (it has exactly one STEMMA QT port, on the end of the board). In the REPL, `import board; i2c = board.STEMMA_I2C(); i2c.try_lock(); print([hex(a) for a in i2c.scan()])` should print `['0x5a']`. |
| Driver found, motor silent | Motor leads not making contact at the pads (see the solder-free caveat); pattern renders to an empty effect list (`UNMAPPED_HIGH` and `NONE` are silent on purpose); you sent a frequency outside every band. |
| Everything works but feels weak | 3.3 V drive of a motor rated to 5 V; try effects with higher percentages first. Powering the driver's VIN from 5 V is possible but needs soldering, so it is out of scope for this build. |
| `calibration_profile.json not found` | Copy it to the root of `CIRCUITPY`, not into `lib/`. |
| Board reports `calibration_profile.json is malformed` | The board's loader needs the same four keys per band as the laptop's. Run `python validate_calibration.py --check-only calibration_profile.json` on the laptop and fix what it reports, then copy the file over again. |
