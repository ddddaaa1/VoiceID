# ADR 0008: Use speaker-disjoint LibriSpeech clean subsets for the first public evaluation

- Status: Accepted
- Date: 2026-08-25

## Context

VoiceID needs a reproducible, public first corpus before it can publish measured calibration results. The corpus must be downloadable by reviewers, legally attributable, large enough for a multi-speaker protocol, and separate development from evaluation speakers. Raw audio must not be committed to Git.

The current ECAPA encoder was trained upstream on VoxCeleb, so VoxCeleb alone would not provide an independent first evaluation. Common Voice is intended for speech recognition and its current terms restrict attempts to determine speaker identity, making it unsuitable for this biometric experiment.

## Decision

Use LibriSpeech `dev-clean` for development threshold selection and `test-clean` for held-out evaluation. The importer:

- accepts only mono 16 kHz FLAC source recordings;
- selects speakers and clips with a documented SHA-256 ordering seed;
- keeps development and evaluation speakers disjoint;
- assigns every selected recording exclusively to enrollment or probe;
- writes signed 16-bit PCM WAVE files accepted by the VoiceID pipeline;
- creates one genuine and one deterministic impostor comparison per probe;
- binds every output file to the manifest with SHA-256;
- records source archives, official MD5 checksums, license, selection parameters, selected speakers, manifest digest, and limitations.

LibriSpeech's CC BY 4.0 distribution is recorded as dataset-level authorization for public research. It is not represented as individual consent for biometric deployment.

## Consequences

The experiment is reproducible and its calibration and evaluation roles are explicit. Reviewers can regenerate the exact trial collection without receiving audio through GitHub.

Read English audiobooks are a narrow, relatively clean condition. Results cannot establish performance for conversational speech, microphones, languages, noise, replay, synthetic speech, or production biometric use. A separately consented first-party corpus and anti-spoofing evaluation remain required.
