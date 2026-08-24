# ADR 0001: Use a Replaceable Audio Preprocessing Pipeline

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Speaker encoders and anti-spoofing models require consistent audio, but clients may send different containers, sample rates, channel layouts, durations, and signal qualities. Audio decoding also handles untrusted binary input and therefore forms a security boundary.

The first development increment needs deterministic behavior and fast tests without introducing heavyweight system dependencies. Production inference will eventually require better resampling, neural voice activity detection, and broader codec support.

## Decision

Define audio decoding and voice activity detection as ports. Implement an initial adapter that:

- accepts bounded, uncompressed 16-bit PCM WAVE payloads;
- converts stereo input to mono;
- resamples to 16 kHz with deterministic linear interpolation;
- removes DC offset and applies bounded peak normalization;
- detects speech with an energy-based baseline;
- reports speech duration, speech ratio, clipping, and approximate SNR.

The application service depends only on the ports. A future FFmpeg decoder, soxr resampler, or Silero VAD adapter can replace a baseline component without changing enrollment or verification use cases.

## Consequences

### Positive

- Domain and application tests do not download models or require native libraries.
- Input constraints and quality behavior are explicit and auditable.
- Neural and DSP implementations can be benchmarked behind stable contracts.
- The inference pipeline remains testable with synthetic signals.

### Negative

- Linear interpolation is not a production-quality resampler.
- Energy-based VAD is sensitive to stationary noise and non-speech sounds.
- The initial decoder supports only a narrow, well-defined input format.

These limitations are intentional and documented. They provide a measurable baseline rather than pretending that the first implementation is production-ready.
