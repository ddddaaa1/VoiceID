# ASVspoof 2019 LA — VoiceID AASIST v1

## Status

Complete measured research result. All 96,081 official development and evaluation trials were
scored end to end, every source FLAC is hash-bound, and the pooled evaluation EER and min t-DCF
match the pinned upstream evaluator exactly. This result does not enable the production policy.

## Question

How does VoiceID's pinned AASIST adapter perform end to end on the official ASVspoof 2019 Logical
Access development and held-out evaluation protocols, and what is its effect under the organizer's
fixed-ASV t-DCF model?

## Frozen inputs

- Dataset: ASVspoof 2019 LA, DOI `10.7488/ds/2555`, ODC-By 1.0.
- Publisher archive: 7,640,952,520 bytes; MD5
  `30c98f11d8b2bc21f2c257bfd78bb5c5`.
- Locally verified archive SHA-256:
  `208a7e4e3913f8c75ae1afd19bf32a5b29ae68435e9e30e23e5e98b6a155e4ec`.
- Development: 24,844 trials (2,548 bona fide; 22,296 spoof).
- Evaluation: 71,237 trials (7,355 bona fide; 63,882 spoof).
- Countermeasure: `clovaai/aasist-asvspoof2019-la@a04c9863`.
- Checkpoint SHA-256:
  `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0`.
- Pipeline: `asvspoof2019-la-flac-pad64600-aasist-v1`.

Development and evaluation speakers are disjoint. The development partition selects the VoiceID
application operating threshold; the evaluation partition remains held out. Official pooled and
attack-level EER/t-DCF use the evaluation partition and organizer-provided fixed-ASV scores.

## Measured results

| Metric | Result |
|---|---:|
| Development softmax-score EER | 0.470947% |
| Held-out softmax-score EER | 0.815669% |
| Held-out upstream class-1-logit EER | 0.829511% |
| Held-out minimum normalized t-DCF | 0.0275295 |
| Fixed-ASV EER | 2.457784% |
| Development-selected softmax threshold | 0.592899654 |
| Held-out bona-fide reject rate at locked threshold | 0.203943% (15/7,355) |
| Held-out spoof accept rate at locked threshold | 6.295983% (4,022/63,882) |

The application threshold was selected once on development and applied to evaluation unchanged.
Its held-out spoof accept 95% Wilson interval is 6.110247%–6.486976%; the bona-fide reject interval
is 0.123635%–0.336240%. The post-hoc evaluation optimum is materially different
(`0.010637551`), so it is reported only as a distribution-shift diagnostic and is not a deployable
threshold. A18 is the hardest individual held-out attack by EER (2.607636%) and min t-DCF
(0.0808480); A09 observes zero error in this frozen condition, which does not imply universal
resistance to that attack family.

The pinned upstream `evaluation.py` at revision `a04c9863` produced EER `0.8295112264154778%` and
min t-DCF `0.0275294779020878`; VoiceID produced the same values with zero numeric delta. The
upstream evaluator file used for this independent check has SHA-256
`008d92a04bbea3bf5074017d58127f0d271ff114ca39af69a72f4779cf4b73f8`.

Inference ran on Apple Metal with batch size 32 and completed the final uninterrupted session at
37.49 trials/second. The transactional ledger resumed correctly after deliberate interruptions.
An eight-file CPU/MPS smoke comparison observed maximum absolute deltas of `3.82e-6` for logits and
`1.32e-10` for softmax scores; this small check is not a platform-wide determinism guarantee.

## Evidence publication boundary

| Artifact | Publication | Purpose |
|---|---|---|
| `acquisition.json` | Public | Publisher identity, archive checksums, extraction bounds, and license. |
| `countermeasure-report.json` | Public | Development-calibrated aggregate metrics and held-out attack categories. |
| `tandem-report.json` | Public | Aggregate pooled and A07–A19 EER/min-tDCF under the fixed-ASV context. |
| `provenance.json` | Public | Dataset, protocols, model, pipeline, artifact hashes, and interpretation boundary. |
| `source-inventory.jsonl` | Local only | Per-audio paths, byte sizes, and SHA-256 values. |
| `spoof-scores.json` | Local only | Per-trial softmax scores and metadata. |
| `official-cm-scores.txt` | Local only | Per-trial raw logits used for upstream validation. |

The local-only artifacts are reproducible from the official corpus and the committed runner, but
are ignored by Git because they contain per-recording hashes or biometric-derived model outputs.
The public aggregate reports preserve the measured outcome without publishing those rows.

## Policy decision

Default anti-spoof fusion remains disabled. The strong in-domain pooled EER and t-DCF demonstrate
that the adapter and metric pipeline work, but the development-selected operating threshold does
not transfer safely to the unseen evaluation attacks. The corpus also excludes replay, modern
generators, deployment codecs, microphones, languages, demographic analysis, and active liveness.
Enabling a security policy from this single 2019 LA condition would overstate the evidence.

Raw audio, per-trial derived evidence, and the SQLite restart ledger are deliberately excluded from
Git. Reported figures describe this frozen research condition only; they do not prove liveness,
identity, replay resistance, or generalization to contemporary generators, codecs, languages,
microphones, or deployment traffic.
