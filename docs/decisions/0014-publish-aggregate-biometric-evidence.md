# ADR 0014: Publish Aggregate Biometric Evidence Only

- Status: Accepted
- Date: 2026-08-25

## Context

The end-to-end ASVspoof experiment produces two classes of evidence. Aggregate reports describe
error rates, confidence intervals, attack breakdowns, t-DCF, model lineage, and artifact hashes.
Per-trial artifacts contain one model output for every recording, while the source inventory binds
individual audio paths to content hashes. The source corpus is public, but those rows remain
biometric-derived data and are unnecessary for a client to review the architecture or conclusions.

Publishing every row would also add roughly 48 MB to the Git history. The runner and official
corpus already provide a reproducible path for an authorized reviewer who needs those artifacts.

## Decision

Commit `acquisition.json`, `countermeasure-report.json`, `tandem-report.json`, and
`provenance.json`. Keep `source-inventory.jsonl`, `spoof-scores.json`, and
`official-cm-scores.txt` local and explicitly ignored by Git. Never commit raw corpus audio or the
SQLite scoring ledger.

The public experiment README must identify both publication classes. The model release registry
verifies only committed aggregate evidence. Artifact-level hashes in provenance may bind local
outputs without exposing their rows.

## Consequences

Public reviewers can verify the measured results, official metric agreement, model identity,
protocol hashes, acquisition integrity, and policy decision. They cannot inspect each score without
re-running the committed pipeline against the official corpus. That tradeoff is intentional: a
public portfolio does not need per-recording biometric-derived data to demonstrate the engineering
work.
