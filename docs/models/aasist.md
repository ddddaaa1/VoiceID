# AASIST Countermeasure Model Card

## Model identity

- **VoiceID model ID:** `clovaai/aasist-asvspoof2019-la@a04c9863`
- **Upstream project:** [clovaai/aasist](https://github.com/clovaai/aasist)
- **Upstream revision:** `a04c9863f63d44471dde8a6abcb3b082b07cd1d1`
- **Checkpoint SHA-256:** `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0`
- **Vendored architecture SHA-256:** `9e0d3e80937dd0577beea7883098465a479da23a198ebc0d712abcc59b0bec50`
- **License:** MIT; the upstream notice is preserved in `LICENSES/AASIST.txt`.
- **Paper:** [AASIST: Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks](https://arxiv.org/abs/2110.01200)

VoiceID vendors the exact upstream architecture and official `AASIST.pth` checkpoint so that a
release does not silently change when a remote repository changes. Runtime loading verifies the
checkpoint hash before deserialization.

## Intended use

The adapter is an experimental presentation-attack countermeasure for research and portfolio
evaluation. It produces an uncalibrated score for a 16 kHz waveform. Higher values mean that the
upstream classifier assigns relatively more evidence to its spoof class.

The adapter is not enabled by the default verification policy. A softmax value is not a calibrated
probability, and the upstream results are not VoiceID results. Step 8C must measure the complete
VoiceID pipeline on an official, held-out protocol before any operating threshold can be considered.

## Input and output contract

- Mono waveform at exactly 16 kHz.
- The countermeasure receives the resampled waveform before speaker-model peak normalization or
  VAD segment extraction.
- Inputs are deterministically repeated or truncated to 64,600 samples, matching upstream
  evaluation.
- The upstream output ordering is `(spoof, bonafide)`.
- VoiceID applies a numerically stable two-class softmax and exposes the spoof-class value in
  `[0, 1]`.
- Corpus scoring also preserves the raw class-1 bona-fide logit used by the pinned upstream
  evaluator; it is never presented as a calibrated probability.
- Batch inference changes throughput only. Each waveform receives the same deterministic padding
  and an independently recorded score.
- The model identifier is attached to every attempt on which this adapter runs.

## Validation in this repository

Automated tests check sample-rate enforcement, exact input sizing, class direction, finite output,
single and batch inference equivalence, failure isolation, checkpoint integrity, and a real CPU
inference using the packaged official weights. The end-to-end ASVspoof runner additionally checks
protocol counts, speaker disjointness, source hashes, resumability, and official t-DCF lineage.

## Known limitations

- The checkpoint was trained for the ASVspoof 2019 Logical Access domain. It should not be assumed
  to generalize to replay attacks, new generators, unseen codecs, microphones, languages, or
  adversarial transformations.
- Repeating short clips can create artificial periodic structure; this is retained only to match
  the upstream evaluation recipe.
- A single-file countermeasure does not establish liveness. Challenge-response and session-level
  signals remain separate controls.
- Demographic, device, language, and accessibility impacts have not been evaluated.
- Model deserialization and inference are local, but biometric inputs remain sensitive data.

## Safe interpretation

Do not present the score as proof that audio is authentic. Until a frozen VoiceID evaluation
supports a policy, the API must continue to return `spoof_check_not_run` by default and must not
market anti-spoofing as an active security guarantee.
