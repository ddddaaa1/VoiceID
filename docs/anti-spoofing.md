# VoiceID Anti-Spoofing Protocol

VoiceID treats speaker verification and presentation-attack detection as independent models. A high speaker score answers who the voice resembles; a countermeasure score estimates whether the signal is bona fide or attacked. Neither score can substitute for the other.

## Delivery stages

- **Step 8A — Countermeasure score contract and metrics:** implemented.
- **Step 8B — Concrete pretrained detector adapter:** implemented.
- **Step 8C1 — Official metric and reference-score reproduction:** implemented.
- **Step 8C2 — End-to-end AASIST corpus evaluation:** the reproducible runner is implemented;
  measured artifacts remain pending completion of the local corpus run.

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

For corpus evaluation, the runtime scores batches while preserving the same 64,600-sample input
recipe. A transactional SQLite ledger commits only complete protocol-order batches, verifies that
resume state is an exact prefix, and prevents a model, protocol, or pipeline change from reusing
incompatible scores. The final publisher binds every trial to the SHA-256 of its compressed FLAC
source and writes artifacts atomically.

VoiceID publishes two score views from the same inference. `spoof_probability` is the stable
two-class softmax value used by the application contract, where higher means more likely spoof.
`official_cm_score` is the upstream class-1 bona-fide logit used for ASVspoof comparison, where
higher means more likely bona fide. The report never silently treats these different rankings as
the same score.

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

This countermeasure cost is deliberately not called tandem DCF. VoiceID now also implements the
official fixed-ASV normalized t-DCF formulation with arbitrary bona-fide-support scores. Its result
was validated on all pooled ASVspoof 2021 LA evaluation trials against the organizer's reference
implementation. See the
[frozen reference reproduction](../experiments/asvspoof2021-la-reference-v1/README.md).

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

## Official corpus evaluation

Step 8 uses the official [ASVspoof challenge](https://www.asvspoof.org/) protocols. Logical Access
covers synthetic and voice-converted speech, Physical Access covers replay, and the Deepfake track
extends generated-speech evaluation under realistic coding conditions. Source protocols and keys
remain authoritative. ASVspoof 2019 is distributed under ODC-By 1.0 at
[DOI 10.7488/ds/2555](https://doi.org/10.7488/ds/2555); its 7,640,952,520-byte LA archive has the
publisher MD5 `30c98f11d8b2bc21f2c257bfd78bb5c5`.

```bash
uv run python scripts/prepare_asvspoof2019_la.py \
  data/raw/asvspoof2019/LA.zip \
  data/raw/asvspoof2019/extracted

uv run python scripts/score_asvspoof2019_la.py \
  data/raw/asvspoof2019/extracted/LA \
  --device mps \
  --batch-size 32 \
  --output experiments/asvspoof2019-la-aasist-v1
```

The archive, extracted FLAC files, and restart ledger stay under ignored `data/raw/`. Only
non-audio evidence artifacts are eligible for Git. Fusion remains disabled until the completed
report is reviewed against its held-out EER, t-DCF, attack breakdown, and limitations.
