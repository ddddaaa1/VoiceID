# ADR 0013: Checkpoint Corpus Inference Without Weakening Evidence

## Status

Accepted on 2026-08-25.

## Context

ASVspoof 2019 LA development and evaluation contain 96,081 trials. A complete AASIST run can take
long enough to be interrupted by a process failure, machine restart, or accelerator error. A simple
append-only text file could resume quickly, but it could also hide a partial write, reordered trial,
changed protocol, or model replacement. Re-running all completed trials wastes compute and makes
operational recovery unnecessarily fragile.

## Decision

Use a local SQLite checkpoint ledger with `FULL` synchronous transactions. Its immutable identity
binds the dataset release, development/evaluation protocol SHA-256 values, countermeasure model ID,
pipeline ID, and expected trial count. Each transaction appends one contiguous inference batch.
Resume is allowed only when stored trial IDs form an exact prefix of the newly loaded official
protocol.

The final evidence publisher requires the full protocol and writes a source inventory, application
score manifest, countermeasure report, upstream-compatible CM scores, official fixed-ASV t-DCF
report, and provenance record atomically. Every source FLAC is represented by its byte size,
relative path, and SHA-256. Audio and the checkpoint remain outside Git.

## Consequences

- Interrupted inference can resume without silently skipping or mixing trials.
- Batch size and accelerator choice affect throughput but not trial order or preprocessing.
- Protocol, model, or pipeline changes require a new ledger and experiment version.
- The ledger is local operational state, not publishable accuracy evidence by itself.
- Publishing waits for all trials and therefore cannot misrepresent a partial run as a benchmark.
