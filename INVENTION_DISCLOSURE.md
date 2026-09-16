# Invention disclosure: audio-to-haptic translation calibrated to an individual's own sound-to-touch associations

**Working document, written 2026-09-16 from the state of this repository.** It records the
invention as currently understood so that a patent professional can evaluate it. It is not
legal advice, and it deliberately does not overstate what has been built or what is new.
Fill in the bracketed fields before sharing it.

| | |
|---|---|
| Inventor(s) | *[legal name, address, citizenship]* |
| Date of this disclosure | 2026-09-16 |
| Date of conception | *[earliest dated record of the idea: notes, sketches, chat logs, the first commit]* |
| Earliest public disclosure | *[when this repository became public, if it is; any demo, post, or conversation with someone not under confidentiality]* |
| Reduction to practice | Software prototype confirmed working by the inventor via live microphone test. Hardware not yet built. No real calibration data collected yet. See §3.6. |

## 1. Summary

A system that translates sound into touch, in which the mapping from sound *content*
(audio frequency bands) to haptic *pattern* is not chosen by an engineer but calibrated to
one specific person's own reported cross-modal associations: what each range of
frequencies feels like to that person. A calibration procedure elicits those associations
and stores them as a personal profile (a list of frequency bands, each with the person's
verbatim tactile description and the haptic pattern that matches it). At runtime, live
audio is analysed (FFT), the dominant frequency is looked up in that person's profile, and
a haptic actuator renders the resulting pattern.

The contribution claimed is narrow and specific: **using the individual's own
sound-to-touch association as the calibration target for the content mapping.** The
prior art personalizes intensity, waveform fidelity, or device response; it does not
personalize which sound maps to which felt pattern, and it does not use a person's
cross-modal report to do so.

## 2. Problem

Existing audio-to-haptic systems (game and media haptics, accessibility aids for
hearing-impaired users, phone haptics) derive vibration from audio through a mapping that
is fixed at design time and identical for every user, possibly scaled per user for
intensity or threshold. Users who have sound-to-touch synesthesia experience a specific,
stable tactile quality for a given sound; a generic mapping that renders a frequency they
experience as "sharp, pointed" as a slow rumble is incongruent with their perception. The
working hypothesis behind this project is broader: that many people have consistent, if
weaker, cross-modal sound-to-touch associations, and that a haptic rendering congruent
with a person's own associations is more legible and more acceptable than a generic one.
No existing system known to the inventor asks the person what a sound feels like and
builds the content mapping from the answer.

## 3. Description

### 3.1 Pipeline

```
 audio in ──▶ FFT per ~23 ms block ──▶ dominant frequency (Hz)
                                              │
                        personal calibration  ▼  profile: [{freq_low, freq_high, feeling, pattern}, ...]
                                              │  half-open bands, first match wins, else NONE
                                              ▼
                                    haptic pattern name  ──▶ actuator rendering layer ──▶ motor
```

The implementation in this repository is `haptic_prototype.py` (laptop: microphone
capture, FFT, lookup, terminal output) and `firmware/qtpy_drv2605/code.py` (microcontroller:
same lookup, drives a DRV2605L haptic controller and a vibration motor).

### 3.2 The calibration procedure (Phase 0 self-test)

The personal profile is produced by an elicitation procedure, as currently conceived:

1. Present the person with audio stimuli confined to one frequency band at a time (pure
   tones or slow sweeps, band-limited noise, or band-filtered excerpts of real material),
   at a controlled playback level and through a known transducer.
2. Ask what the sound **feels like**, not what they would like: the person reports, in
   their own words, the tactile quality the sound evokes (texture, temporal shape, location
   in the body). This verbatim report is stored as the band's `feeling`.
3. Ask the person to pick, from a vocabulary of renderable haptic patterns (or by
   describing one to be added), the pattern that matches the reported feeling. Its name is
   stored as the band's `pattern`.
4. Band edges are placed where the reported quality changes as frequency moves, rather
   than being fixed in advance.
5. Repeat the procedure after an interval. Bands whose reports are stable across sessions
   are the person's calibration; unstable bands are flagged or left unmapped.
6. Write the result as the profile file described in §3.3.

The instruction in step 2 is the heart of the method. The profile is a record of
perception, elicited the way a psychophysics experiment elicits a judgement, not a
preference setting.

### 3.3 Data structure

The profile is a JSON array of band objects, each `{freq_low, freq_high, feeling, pattern}`;
the exact schema is in `docs/calibration-data-format.md`. Bands are half-open
`[freq_low, freq_high)`, checked in order, first match wins, and a frequency in no band
yields the reserved pattern `NONE`. Overlaps are rejected; gaps are allowed and mean "not
mapped". The same pattern may legitimately appear in non-adjacent bands, so the mapping
need not be monotonic in frequency. The file carries no metadata by design; provenance is
recorded alongside it.

### 3.4 Runtime

Audio is captured at 44.1 kHz in blocks of 1024 samples (about 23 ms, giving roughly 43 Hz
frequency resolution). Each block is transformed with a real FFT, the bin with the largest
magnitude gives the dominant frequency, the dominant frequency is looked up in the
profile, and the resulting pattern name is passed to the actuator layer. In the prototype
the actuator layer is a printed line; in the firmware it is a table from pattern name to
DRV2605L waveform-library effect sequence, played on an eccentric-rotating-mass motor.

### 3.5 Two layers, kept separate

The design separates two mappings that prior systems tend to fuse:

- **Personal content layer**: frequency band → felt pattern name, specific to one person,
  produced only by that person's calibration, stored as a device-independent file that is
  identical on the laptop and the microcontroller.
- **Actuator rendering layer**: pattern name → drive waveform for a particular motor and
  driver, generic engineering, tuned per device.

The claim is about the first layer. The second is ordinary and is what most of the prior
art below is about.

### 3.6 What has actually been built, honestly

- Phase 1 software prototype (`haptic_prototype.py`): pipeline confirmed working by the
  inventor via live microphone test before this document was written. An automated test
  (`tests/test_pipeline.py`) feeds synthetic tones through the same code path and confirms
  each band of the profile is reached.
- Phase 2 firmware (`firmware/qtpy_drv2605/code.py`): written and tested under CPython with
  the hardware modules stubbed; not yet run on a board. The hardware has not been
  purchased or wired (`docs/hardware-setup.md`).
- **No real calibration profile exists yet.** The profile in the repository is placeholder
  data written by an engineer, i.e. exactly the generic mapping the invention argues
  against. The Phase 0 self-test has not been run. Consequently the inventive concept is
  described here but has not been actually reduced to practice with real cross-modal data,
  and the key evidence for the claim (that a personally calibrated content mapping differs
  from a generic one, is stable for a person, and differs between people) has not been
  gathered. §8 lists what to collect.

## 4. Prior art already identified

These references were found by the inventor's own research. Characterizations below are
of what each reference is understood to teach; the actual claims of each must be read
before relying on any of this, and the list is not the result of a professional search.
No additional references have been added here that were not actually researched.

| Reference | Understood to teach | What it personalizes | Why this invention differs |
|---|---|---|---|
| US 7,623,114; US 8,441,437; US 8,686,941 (Immersion) | Mapping audio frequency bands to distinct haptic sensations via FFT, for games and media. | Nothing per user: the band-to-sensation assignment is fixed by the designer. | This invention uses the same kind of band analysis, but the band-to-pattern assignment comes from the individual's own reported association, not from the designer. This family is the closest structural match and the one any claim must be drafted around. |
| US 9,083,821 (Immersion) | Frequency-warping audio into haptic output for hearing-impaired users. | Nothing per user: one warp for a population. | Different goal (make audio perceptible as vibration) and no per-person calibration of content. |
| US 10,754,428 B1 | Perceptual frequency-warping so the haptic frequency perceptually matches the audio frequency. | Perceptual fidelity: the target is *matching the audio*. | The target here is not matching the sound but matching the person's association with the sound, which may be nothing like the sound's own frequency. |
| US 2016/0259480 A1 (Apple) | Calibrating the haptic waveform to a specific device's physical and structural properties. | The device. | Personalizes hardware response, not the person or the content mapping. |
| US 11,011,075 (Meta) | A per-individual calibration curve mapping a subjective force value to a sensor voltage. | Intensity, per individual. Closest on "calibrated to the individual". | The calibrated variable is magnitude (how strong), not content (which pattern for which sound). |
| Samsung, Korean application published 2025 *[number to be confirmed]* | Calibrating haptic intensity thresholds from a user profile plus exercise and biometric data. | Intensity thresholds, per user, from biometrics. | Again magnitude, and derived from biometric data rather than from the user's reported cross-modal perception. |

**The gap.** Every reference either fixes the content mapping for all users (Immersion,
US 10,754,428) or personalizes something other than content: intensity (Meta, Samsung),
perceptual frequency fidelity (US 10,754,428), or the device (Apple). None uses, as the
calibration target, an individual's own reported association between a sound and a
tactile quality. That is the claim, and only that.

## 5. Statement of the claimed contribution

A method and system for haptic rendering of audio in which the assignment of haptic
patterns to audio frequency bands is (a) derived from a specific individual's reported
tactile associations with audio stimuli in those bands, elicited by a defined procedure,
(b) stored as a profile specific to that individual, and (c) applied at runtime to select
the haptic pattern for each analysed segment of an audio signal, the selected pattern then
being rendered on an actuator.

What is **not** claimed: FFT-based band analysis as such; mapping bands to sensations as
such; per-user intensity or threshold calibration; device-response calibration;
perceptual frequency matching; any particular actuator, driver, or waveform.

## 6. Draft claim concepts

For discussion with counsel. These are concepts, not claim language.

**Independent (method).** Generating haptic output from an audio signal by:
(a) for each of a plurality of audio frequency bands, presenting to a specific user an
audio stimulus substantially confined to the band, and recording (i) a tactile descriptor
reported by the user as characterizing the tactile sensation the user associates with the
stimulus and (ii) an identifier of a haptic pattern, from a set of renderable patterns,
corresponding to the reported descriptor;
(b) storing the bands, descriptors and identifiers as a calibration profile specific to
the user;
(c) receiving an audio signal and determining, for successive time segments, a dominant
frequency;
(d) selecting, for each segment, the identifier of the band of the user's profile that
contains the dominant frequency; and
(e) driving a haptic actuator with a waveform associated with the selected identifier.

**Independent (system).** A haptic device comprising storage holding a user-specific
profile of the above form, a processor configured to perform (c) to (e), and an actuator.

**Dependent concepts.**
- The elicitation instructs the user to report perceived tactile quality rather than
  preference.
- The elicitation is repeated after an interval and only bands with consistent reports
  are retained (test-retest validation).
- Band edges are set at the frequencies where the user's reported descriptor changes.
- The profile assigns the same identifier to non-adjacent bands, or otherwise is not
  monotonic in frequency.
- Profiles of at least two users assign different identifiers to the same band (the
  mapping is not derivable from a population-level rule).
- The profile is a device-independent file, and the identifier-to-waveform mapping is
  stored separately per actuator (the two-layer architecture of §3.5).
- The audio signal is live microphone input; or media playback; or speech.
- The descriptor includes a body location and the actuator, or one of several actuators,
  is chosen accordingly (not yet implemented).

## 7. Honest assessment of patentability

**This claim is narrow and sits next to a lot of prior art.** It will need precise
language to survive examination, and it may not.

- **Obviousness (35 U.S.C. §103) is the main risk.** An examiner can combine the Immersion
  band-to-sensation mapping with per-user calibration from Meta or Samsung and argue that
  personalizing the mapping is an obvious extension, or mere user customization. The
  answer has to be that the calibration *target* is qualitatively different (a cross-modal
  perceptual report, not a preference or a magnitude) and that the outcome is not
  predictable from the prior art: that a person's profile is stable over time, that
  profiles differ between people in ways no population rule produces, and that the
  congruent mapping measurably works better. None of that evidence exists yet (§8).
- **Unsearched prior art that could be closer than anything listed.** User-configurable
  haptics are common: phones let users assign vibration patterns to contacts and alerts;
  games let users adjust rumble; accessibility settings expose haptic options. Any prior
  system that let a user assign a vibration pattern per frequency band or per sound type
  (a "haptic equalizer") would be very close, and the line between "preference" and
  "reported association" would be argued over. Academic sensory-substitution work has
  mapped audio frequency bands to vibrotactile channels on the body for decades (for
  example the "Model Human Cochlea" / Emoti-Chair line of work by Karam, Russo and Fels,
  c. 2009, cited here from memory and to be verified), and the synesthesia literature
  documents sound-to-touch synesthesia without, as far as the inventor knows, using it to
  calibrate a device. All of this must be searched before filing.
- **Abstract-idea rejection (35 U.S.C. §101).** Collecting reports and mapping data can be
  characterized as an abstract idea or a mental process. Claims should be tied to the
  stimulus presentation apparatus, the signal analysis, and the physical actuator, and the
  specification should frame the contribution as an improvement in the haptic device's
  function, not in the information.
- **Do not put "synesthesia" in a claim.** It names a neurological condition that an
  examiner cannot examine and an infringer cannot be tested for. Claim the procedure
  (stimulus, reported tactile descriptor, selected pattern) and the data structure; use
  synesthesia in the specification as the motivating case, and state that the method
  applies to any individual's consistent cross-modal association.
- **Written description and enablement.** The specification must describe the elicitation
  protocol concretely: stimuli, levels, transducer, instructions, how band edges are
  chosen, how the pattern vocabulary is presented, how stability is checked. A claim that
  rests on "calibrate to the user's perception" with no protocol is a black box.
- **Design-around.** Even if granted, a competitor offering "choose the vibration you like
  for bass" arguably falls outside a claim drafted around perceived association. The value
  is more likely in a specific, defensible protocol plus data structure plus demonstrated
  benefit than in a broad concept.
- **Public disclosure clock.** If this repository is public, or the idea has been shown or
  described to anyone not under confidentiality, that may count as public disclosure. In
  the United States there is a one-year grace period from the inventor's own disclosure;
  most other jurisdictions have no grace period at all. If foreign rights matter, get
  advice before disclosing further. A provisional application is the usual inexpensive way
  to fix a priority date while the evidence in §8 is gathered; it lasts twelve months.

## 8. Evidence that would strengthen a filing

In rough order of importance:

1. **The inventor's own profile** from an actual Phase 0 self-test, replacing the
   placeholder. Until this exists the project has no real calibration data.
2. **Test-retest stability**: the same person, the same procedure, weeks apart. Stability
   is what makes the profile a trait rather than a mood.
3. **Inter-subject variation**: profiles from several people (the planned friends' survey)
   showing that the same band is assigned different patterns by different people. This is
   the direct evidence that a generic mapping cannot serve everyone.
4. **A comparison**: the same audio rendered through a person's own profile versus the
   placeholder (generic) profile, measured by a task (identify sound categories by touch
   alone) or by congruence ratings. An advantage here is the "unexpected result" that
   answers an obviousness rejection.
5. **A working hardware demonstration** (Phase 2), which is actual reduction to practice.
6. **Dated records** of all of the above. Git history is timestamped; keep survey responses
   and notes dated too, and keep the real profile and study data confidential until a
   filing decision is made if foreign rights matter.

## 9. Questions for a patent professional

- File a provisional now on the concept and protocol, or wait for the §8 evidence?
- Has the repository's visibility, or any conversation, already started a disclosure
  clock, and what does that do to non-US rights?
- Method, system, or data-structure (computer-readable medium) claims, or all three?
- Is the elicitation protocol claimable on its own as a calibration method, separately
  from the runtime system?
- Scope of the professional prior-art search: consumer haptic customization features,
  accessibility features, haptic-equalizer products, sensory-substitution research,
  synesthesia-based interface work.

## 10. Disclaimer

This document was drafted from the repository's code and the inventor's own prior-art
research. It is a description of the invention for evaluation purposes, not a legal
opinion on patentability, freedom to operate, or inventorship. Nothing in it should be
relied on without review by a registered patent attorney or agent.
