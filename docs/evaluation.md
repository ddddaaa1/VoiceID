# VoiceID Evaluation and Calibration Protocol

VoiceID separates **scoring**, **calibration**, and **final evaluation**. This prevents the held-out evaluation set from influencing the threshold it is supposed to measure.

## Current delivery state

Step 7A implements the strict scored-trial contract, validation rules, FAR, FRR, observed EER, normalized minDCF, development-only threshold selection, held-out reporting, and condition breakdowns. Step 7B adds a hashed audio-trial contract and generates scores through the versioned preprocessing, enrollment, verification, and ECAPA pipeline. Step 7C begins with a reproducible LibriSpeech clean-subset importer; measured results and confidence intervals are still pending.

No bundled value is a VoiceID benchmark. `examples/evaluation/scored-trials.example.json` contains deliberately synthetic scores used to exercise the contract.

## Audio-trial manifest v1

`voiceid-audio-trials/v1` binds every logical trial to specific PCM WAVE bytes before inference. Start from `examples/evaluation/audio-trials.example.json`; its paths and hashes are placeholders and are not directly runnable.

The dataset metadata requires an ID, immutable version, and authorization or consent attestation. Public-corpus licensing must be described honestly and must never be presented as individual biometric consent. Each enrollment declares an identity, true speaker, partition, and three to eight unique recordings. Each trial declares its claimed identity, true probe speaker, expected label, condition, and probe recording.

Every recording reference contains a safe relative `.wav` path and lowercase SHA-256 digest. The manifest is resolved relative to its own directory. Absolute paths, parent traversal, missing files, symlink escapes, empty files, files over the configured limit, and checksum mismatches fail before inference.

Protocol validation also rejects:

- speakers or audio content shared between development and evaluation;
- enrollment audio reused as a probe;
- identical audio attributed to different speakers;
- trials crossing partitions or referencing unknown identities;
- duplicate trial or enrollment identity IDs;
- enrollment sets with duplicate recordings;
- labels that conflict with the declared speakers.

The same probe may be compared against multiple claimed identities inside one partition. This is required for impostor trials, but its digest must always represent the same true speaker.

## Generate real ECAPA scores

Place the manifest beside its referenced `audio/` directory and replace every example digest with the output of:

```bash
shasum -a 256 path/to/sample.wav
```

Then run:

```bash
uv run python scripts/score_audio_trials.py path/to/audio-trials.json \
  --output /tmp/voiceid-scored-trials.json \
  --report /tmp/voiceid-evaluation-report.json \
  --device cpu
```

The runner constructs templates through `EnrollmentService`, obtains probe scores through `VerificationService`, records the actual model and pipeline identifiers, and writes a scored manifest accepted by Step 7A. The optional report is calibrated only after all scores exist.

An enrollment rejection, invalid asset, checksum mismatch, model-version inconsistency, quality failure, or missing speaker score fails the complete run. Trials are never silently removed because excluding failures would bias the reported system performance.

## Prepare the public LibriSpeech cohort

Download and verify the official `dev-clean.tar.gz` and `test-clean.tar.gz` archives from [OpenSLR SLR12](https://www.openslr.org/12/), then extract them outside Git. Generate the deterministic VoiceID cohort with:

```bash
uv run python scripts/prepare_librispeech.py \
  --dev-clean data/raw/librispeech/LibriSpeech/dev-clean \
  --test-clean data/raw/librispeech/LibriSpeech/test-clean \
  --output data/raw/librispeech/voiceid-clean-v1
```

The default protocol selects 10 speakers from each subset, three enrollment clips and three probe clips per speaker, and recordings between 2.5 and 12 seconds. Candidates must also pass the exact VoiceID preprocessing pipeline and both enrollment and verification quality policies; a rejected candidate is replaced using the same deterministic order. Selection is based on SHA-256 ordering with a fixed seed, not directory order. Every probe creates one genuine and one impostor trial, so the default output has 20 enrollments, 120 balanced trials, and 120 unique WAV recordings.

The generated directory contains `audio-trials.json`, `provenance.json`, and `audio/`. `provenance.json` freezes archive checksums, license, parameters, eligibility pipeline, quality policies, rejected candidates, selected speaker IDs, limitations, and the manifest digest. The importer refuses to overwrite an existing output directory. Both source and generated audio remain under `data/raw/`, which is ignored by Git.

LibriSpeech is read English audiobook speech originally prepared for automatic speech recognition. Its clean condition is useful for a reproducible first measurement but does not represent conversational, multilingual, noisy, replayed, or synthetic-speech production traffic. Its CC BY 4.0 license is dataset-level authorization for this public experiment, not individual consent for biometric deployment.

## Two partitions with different responsibilities

- `development` is used to choose one operating threshold by minimum normalized detection cost.
- `evaluation` is used once with that locked threshold to estimate generalization.

Every speaker identifier appearing in an enrollment or probe must belong to only one partition. The manifest loader rejects any overlap, even when the speaker appears only in an impostor trial. Both partitions must contain genuine and impostor trials.

## Scored-trial manifest v1

The JSON root contains:

| Field | Purpose |
|---|---|
| `schema_version` | Must be `voiceid-scored-trials/v1`. |
| `dataset.id` | Stable dataset or cohort identifier. |
| `dataset.version` | Immutable version for the exact trial collection. |
| `system.model_id` | Speaker encoder that produced every score. |
| `system.pipeline_id` | Audio preprocessing pipeline that produced every score. |
| `trials` | Development and evaluation comparisons. |

Each trial records a unique ID, partition, label, enrollment speaker, probe speaker, cosine score, and condition. A `genuine` label requires equal speaker identifiers; an `impostor` label requires different identifiers. Unknown fields, non-finite scores, scores outside `[-1, 1]`, inconsistent labels, missing classes, duplicate IDs, and speaker leakage fail validation.

## Metrics

At threshold `t`, scores greater than or equal to `t` are matches.

- **FAR:** accepted impostor trials divided by all impostor trials.
- **FRR:** rejected genuine trials divided by all genuine trials.
- **Observed EER:** the observed threshold with the smallest FAR/FRR difference; the reported rate is their mean at that point.
- **DCF:** `C_miss × P_target × FRR + C_fa × (1 − P_target) × FAR`.
- **Normalized DCF:** DCF divided by the cost of the best trivial always-accept or always-reject system.

The default cost model uses `P_target=0.01`, `C_miss=1`, and `C_fa=1`. These values are explicit CLI parameters and must be selected for the intended product risk, not optimized on evaluation results.

The report includes evaluation minDCF only as a diagnostic lower bound. The deployable candidate remains the threshold selected from development trials and its held-out FAR/FRR/cost.

## Run the contract example

```bash
uv run python scripts/evaluate_scores.py \
  examples/evaluation/scored-trials.example.json
```

Write a reproducible JSON artifact:

```bash
uv run python scripts/evaluate_scores.py \
  examples/evaluation/scored-trials.example.json \
  --target-probability 0.01 \
  --false-accept-cost 1 \
  --false-reject-cost 1 \
  --output /tmp/voiceid-evaluation-report.json
```

## Interpretation rules

- Do not compare metrics from different model or pipeline identifiers as if they were one system.
- Do not tune a threshold after reading evaluation results.
- Do not omit quality failures or trials because their scores are inconvenient.
- Do not report the synthetic example or upstream SpeechBrain metrics as VoiceID performance.
- Publish trial counts and error counts with every rate; percentages alone hide small samples.
- Add confidence intervals and subgroup coverage before making performance claims from a real corpus.
