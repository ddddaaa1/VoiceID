# ADR 0011: Preserve a separate waveform for the countermeasure

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The speaker encoder benefits from voice activity detection and peak normalization. An
anti-spoofing model instead depends on channel, silence, amplitude, and synthesis artifacts that
those transformations can remove or alter. Feeding the speaker-model view to AASIST would create a
pipeline different from its documented evaluation recipe and could hide presentation-attack cues.

## Decision

Audio preprocessing produces two explicit views after safe decoding and 16 kHz resampling:

1. a normalized, speech-segmented view for speaker embeddings; and
2. a non-peak-normalized resampled waveform for the countermeasure.

The `SpoofDetector` port accepts the second `AudioBuffer`. Concrete countermeasures own any further
fixed-length transformation required by their model. Tests assert that the two views remain
distinct.

## Consequences

The model boundary makes preprocessing lineage auditable and avoids accidental feature sharing.
It uses additional memory for one waveform copy. Future countermeasures must document whether they
consume this waveform directly or derive a spectrogram or learned frontend from it.
