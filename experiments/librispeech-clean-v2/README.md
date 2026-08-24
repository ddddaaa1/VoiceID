# LibriSpeech Clean Evaluation — VoiceID v2

This directory publishes the first measured VoiceID speaker-verification experiment. It is an exploratory, reproducible clean-speech measurement, not a production biometric benchmark.

## Frozen system and protocol

- Dataset: LibriSpeech `dev-clean` for calibration and `test-clean` for held-out evaluation.
- License: CC BY 4.0; dataset-level research authorization is not individual consent for biometric deployment.
- Cohort: 10 speaker-disjoint speakers per partition.
- Enrollment: five quality-approved clips per speaker; the template builder may reject embedding outliers while retaining at least three.
- Probes: three quality-approved clips per speaker.
- Trials: 30 genuine and 30 impostor comparisons per partition. Each probe participates in one genuine and one impostor comparison.
- Model: `speechbrain/spkrec-ecapa-voxceleb`.
- Pipeline: `pcm-wave-linear-energy-vad-v1`.
- Calibration: minimum normalized DCF on development only, with `P_target=0.01`, `C_miss=1`, and `C_fa=1`.
- Uncertainty: two-sided 95% Wilson score intervals at the locked threshold.

The selection seed, archive checksums, quality policies, rejected candidates, selected speakers, limitations, and manifest checksum are recorded in `provenance.json`.

## Measured result

The development-selected threshold was `0.5494392210719572`. It was then applied to `test-clean` without modification.

| Held-out metric | Observed | Errors / trials | 95% Wilson interval |
|---|---:|---:|---:|
| FAR | 0.00% | 0 / 30 | 0.00%–11.35% |
| FRR | 3.33% | 1 / 30 | 0.59%–16.67% |
| Normalized DCF | 0.0333 | — | Not estimated |

Development genuine scores ranged from `0.549439` to `0.892574` and impostor scores from `-0.051496` to `0.225634`. Held-out genuine scores ranged from `0.485328` to `0.872107` and impostor scores from `-0.137518` to `0.419513`.

Zero observed false accepts does not establish a zero underlying FAR. The interval is wide, trials reuse speakers and templates, and the clean read-English condition is narrow. The evidence is therefore insufficient to replace the application's provisional decision policy. Anti-spoofing was not run.

## Artifacts

| File | Purpose | SHA-256 |
|---|---|---|
| `audio-trials.json` | Hash-locked enrollment and trial protocol; audio omitted | `6e8d2da348e27376201ffb1be5f6b30e76d6d5fce8e19cfc089204988a7168d4` |
| `provenance.json` | Sources, checksums, configuration, exclusions, and limitations | `4cbfc5fccb16fd023b72ec220b8624aea920a0853393a5293dcd423e34e53a43` |
| `scored-trials.json` | Raw cosine scores from the frozen model and pipeline | `0260e6f9a692e919a8a9e682efee65726f88f097979ef9f4e9cc3861beb7d1d7` |
| `evaluation-report.json` | Locked-threshold rates, cost metrics, and confidence intervals | `a9c8ab0236badacaefa2d06a570777272fb7d309c5875cd212313f50c81656ff` |

No raw or converted voice recording is committed to this repository.

## Reproduce

Download `dev-clean.tar.gz` and `test-clean.tar.gz` from [OpenSLR SLR12](https://www.openslr.org/12/). Verify the official MD5 values before extraction:

```text
42e2234ba48799c1f50f24a7926300a1  dev-clean.tar.gz
32fa31d27d2e1cad72775fee3f4849a9  test-clean.tar.gz
```

Prepare the same local audio cohort:

```bash
uv run python scripts/prepare_librispeech.py \
  --dev-clean data/raw/librispeech/extracted/LibriSpeech/dev-clean \
  --test-clean data/raw/librispeech/extracted/LibriSpeech/test-clean \
  --output data/raw/librispeech/voiceid-clean-v2 \
  --dataset-version voiceid-librispeech-clean-v2
```

Confirm that the generated manifest matches the published manifest SHA-256, then reproduce the scores while keeping audio outside Git:

```bash
uv run python scripts/score_audio_trials.py \
  experiments/librispeech-clean-v2/audio-trials.json \
  --audio-root data/raw/librispeech/voiceid-clean-v2 \
  --output /tmp/voiceid-librispeech-clean-v2-scores.json \
  --report /tmp/voiceid-librispeech-clean-v2-report.json \
  --device cpu \
  --confidence-level 0.95
```

Exact floating-point scores can vary across hardware, numerical libraries, or dependency versions. The source selection and every audio byte remain hash-verifiable independently of inference.
