# ASVspoof 2019 LA — VoiceID AASIST v1

## Status

The reproducible scoring and evidence pipeline is implemented. Measured artifacts will be added
only after every official development and evaluation trial has completed and all integrity gates
pass. No result is claimed by this directory yet.

## Question

How does VoiceID's pinned AASIST adapter perform end to end on the official ASVspoof 2019 Logical
Access development and held-out evaluation protocols, and what is its effect under the organizer's
fixed-ASV t-DCF model?

## Frozen inputs

- Dataset: ASVspoof 2019 LA, DOI `10.7488/ds/2555`, ODC-By 1.0.
- Publisher archive: 7,640,952,520 bytes; MD5
  `30c98f11d8b2bc21f2c257bfd78bb5c5`.
- Development: 24,844 trials (2,548 bona fide; 22,296 spoof).
- Evaluation: 71,237 trials (7,355 bona fide; 63,882 spoof).
- Countermeasure: `clovaai/aasist-asvspoof2019-la@a04c9863`.
- Checkpoint SHA-256:
  `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0`.
- Pipeline: `asvspoof2019-la-flac-pad64600-aasist-v1`.

Development and evaluation speakers are disjoint. The development partition selects the VoiceID
application operating threshold; the evaluation partition remains held out. Official pooled and
attack-level EER/t-DCF use the evaluation partition and organizer-provided fixed-ASV scores.

## Expected evidence

| Artifact | Purpose |
|---|---|
| `source-inventory.jsonl` | Exact protocol order, relative FLAC paths, byte sizes, and SHA-256 values. |
| `spoof-scores.json` | VoiceID higher-is-spoof softmax scores for development/evaluation. |
| `countermeasure-report.json` | Development-calibrated application metrics and held-out attack categories. |
| `official-cm-scores.txt` | Evaluation-only, higher-is-bona-fide raw logits compatible with the upstream evaluator. |
| `tandem-report.json` | Pooled and A07–A19 EER/min-tDCF under the official fixed-ASV context. |
| `provenance.json` | Dataset, protocols, model, pipeline, artifact hashes, and interpretation boundary. |

Raw audio and the SQLite restart ledger are deliberately excluded from Git. Once published,
reported figures describe this frozen research condition only; they do not prove liveness,
identity, replay resistance, or generalization to contemporary generators, codecs, languages,
microphones, or deployment traffic.
