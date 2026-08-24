# VoiceID Evaluation and Calibration Protocol

VoiceID separates **scoring**, **calibration**, and **final evaluation**. This prevents the held-out evaluation set from influencing the threshold it is supposed to measure.

## Current delivery state

Step 7A implements the strict scored-trial contract, validation rules, FAR, FRR, observed EER, normalized minDCF, development-only threshold selection, held-out reporting, and condition breakdowns. Step 7B will generate these scores from a real audio corpus through the versioned preprocessing and ECAPA pipeline.

No bundled value is a VoiceID benchmark. `examples/evaluation/scored-trials.example.json` contains deliberately synthetic scores used to exercise the contract.

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
