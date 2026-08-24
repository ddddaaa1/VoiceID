# ADR 0010: Evaluate anti-spoofing independently before tandem fusion

- Status: Accepted
- Date: 2026-08-25

## Context

VoiceID's decision engine can consume an optional spoof probability, but no concrete countermeasure has been selected or measured. Integrating a pretrained detector directly into the API would make its score appear trustworthy before its direction, labels, attack taxonomy, calibration partition, and error metrics were frozen.

Speaker similarity and spoof detection answer different questions. A spoof can match the claimed speaker, and bona fide speech can belong to an impostor. A single pass/fail metric would conceal which subsystem failed.

## Decision

Introduce a strict `voiceid-spoof-scores/v1` contract before adding a concrete model adapter. Define high scores as more likely spoof, require speaker-disjoint development and evaluation partitions, preserve exact attack IDs, and report replay, synthetic, voice-conversion, and unknown attacks separately.

Select the countermeasure threshold by minimum explicit cost on development only. Report held-out bonafide reject rate, spoof accept rate, countermeasure EER, normalized cost, Wilson intervals, and attack-category breakdowns.

Do not describe the standalone countermeasure cost as tandem DCF. Add t-DCF only when one frozen ASVspoof protocol supplies compatible speaker-verification and countermeasure scores.

## Consequences

Any future RawNet2, AASIST, wav2vec, or ONNX adapter must produce the same bounded spoof-probability contract and can be compared without changing policy code. Model failures remain review outcomes rather than silent bona fide decisions.

Step 8A produces no accuracy claim because its bundled scores are synthetic. Step 8B must document model provenance and preprocessing, and Step 8C must publish official-protocol results before anti-spoofing is enabled by default.
