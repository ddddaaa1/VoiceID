# VoiceID Anti-Spoofing Protocol

VoiceID treats speaker verification and presentation-attack detection as independent models. A high speaker score answers who the voice resembles; a countermeasure score estimates whether the signal is bona fide or attacked. Neither score can substitute for the other.

## Delivery stages

- **Step 8A — Countermeasure score contract and metrics:** implemented.
- **Step 8B — Concrete pretrained detector adapter:** implemented.
- **Step 8C — ASVspoof evaluation and tandem decision report:** pending.

The application supports an optional `SpoofDetector` port, safe decision fusion, and an
integrity-checked adapter for the official pretrained AASIST Logical Access checkpoint. The
countermeasure is deliberately not enabled in the default API: its softmax output is uncalibrated
and has not yet been measured through the complete VoiceID pipeline. The default therefore
continues to report `spoof_check_not_run` and `anti_spoofing_enabled=false`.

## AASIST adapter

The adapter consumes the 16 kHz resampled waveform before peak normalization and VAD extraction.
It repeats or truncates input to 64,600 samples exactly as the upstream evaluation code does,
verifies the packaged checkpoint SHA-256 before loading it, and returns the softmax value for the
upstream spoof class. Every attempt records the concrete countermeasure model ID.

See the [AASIST model card](models/aasist.md) for provenance, hashes, validation, intended use, and
limitations. Upstream benchmark figures are not copied into VoiceID results because they do not
measure this repository's end-to-end pipeline.

## Threat categories

The v1 contract uses five explicit categories:

| Category | Meaning |
|---|---|
| `bonafide` | Human speech without a declared presentation attack. |
| `replay` | Previously recorded speech presented through a playback or injection channel. |
| `synthetic` | Text-to-speech or generated speech. |
| `voice_conversion` | Speech modified to resemble another speaker. |
| `unknown` | A spoof whose mechanism is unavailable or intentionally held out. |

`attack_id` preserves the source protocol's exact system or configuration identifier. Category-level reports therefore remain readable without discarding fine-grained attack lineage.

## Spoof-score manifest v1

`voiceid-spoof-scores/v1` records:

- immutable dataset and system versions;
- development and held-out evaluation partitions;
- a true speaker identifier for leakage checks;
- the bonafide/spoof label;
- attack category and source attack ID;
- a finite spoof probability in `[0, 1]`;
- the recording condition.

Higher scores always mean “more likely spoof.” Scores greater than or equal to the operating threshold are rejected as spoof. The strict loader rejects unknown fields, invalid probabilities, duplicate trial IDs, label/category conflicts, missing classes, and speaker overlap between development and evaluation.

## Metrics and calibration

- **Bonafide reject rate:** bona fide trials classified as spoof, divided by all bona fide trials.
- **Spoof accept rate:** spoof trials classified as bona fide, divided by all spoof trials.
- **Countermeasure EER:** the observed threshold with the smallest gap between those two rates.
- **Countermeasure cost:** a configurable weighted risk using the spoof prior and the costs of rejecting bona fide speech or accepting spoofed speech.

The operating threshold minimizes normalized countermeasure cost on development only. Held-out evaluation uses that threshold without modification. Reports include Wilson intervals and an attack-category breakdown.

This countermeasure cost is deliberately not called tandem DCF. Tandem DCF requires speaker-verification and countermeasure scores under one ASVspoof protocol and belongs to Step 8C.

## Run the synthetic contract fixture

```bash
uv run python scripts/evaluate_spoof_scores.py \
  examples/evaluation/spoof-scores.example.json
```

Write a versioned report:

```bash
uv run python scripts/evaluate_spoof_scores.py \
  examples/evaluation/spoof-scores.example.json \
  --spoof-prior 0.5 \
  --bonafide-reject-cost 1 \
  --spoof-accept-cost 1 \
  --confidence-level 0.95 \
  --output /tmp/voiceid-spoof-evaluation.json
```

The example scores are synthetic contract fixtures, not measured VoiceID anti-spoofing performance.

## Planned public evaluation

Step 8 will use the official [ASVspoof challenge](https://www.asvspoof.org/) protocols. Logical Access covers synthetic and voice-converted speech, Physical Access covers replay, and the Deepfake track extends generated-speech evaluation under realistic coding conditions. Source protocols and keys will remain authoritative; VoiceID will add reproducible manifests, hashes, model lineage, confidence intervals, and combined-system reporting.
