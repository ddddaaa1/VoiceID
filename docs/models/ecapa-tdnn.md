# Model Card: ECAPA-TDNN Speaker Encoder

## Model details

| Field | Value |
|---|---|
| Adapter | `SpeechBrainEcapaEmbedder` |
| Upstream model | `speechbrain/spkrec-ecapa-voxceleb` |
| Architecture | ECAPA-TDNN |
| Framework | SpeechBrain / PyTorch |
| Input | Mono speech waveform at 16 kHz |
| Output | 192-dimensional L2-normalized embedding |
| Upstream training data | VoxCeleb1 and VoxCeleb2 |
| Upstream license | Apache-2.0 |

## Intended use

The model supplies speaker representations for VoiceID research, enrollment, verification experiments, threshold calibration, and portfolio demonstrations.

It is not currently approved for access control, financial authorization, forensic identification, surveillance, or other high-impact decisions.

## Processing

1. Decode bounded 16-bit PCM WAVE input.
2. Convert to mono and resample to 16 kHz.
3. Apply DC removal and bounded peak normalization.
4. Detect speech segments.
5. Concatenate detected speech and require a minimum duration.
6. Run `EncoderClassifier.encode_batch` in inference mode.
7. Validate 192 output values and apply L2 normalization.

## Validation status

The integration smoke test has confirmed that the adapter loads the public model and returns a finite, normalized 192-dimensional vector. This proves technical integration only.

No VoiceID accuracy result has been established yet. The EER reported by the upstream model card belongs to the upstream VoxCeleb evaluation and must not be presented as a VoiceID benchmark.

## Known limitations and risks

- Performance may vary across languages, accents, ages, genders, health conditions, microphones, codecs, and noise environments.
- Short samples and speech detected incorrectly can produce unreliable embeddings.
- Similarity alone does not detect replay, synthetic speech, or voice conversion.
- Embeddings are sensitive biometric data and may enable correlation if mishandled.
- A pretrained model can inherit undocumented biases from its training corpus.

## Required evaluation before broader use

- Reproducible genuine/impostor trial manifest.
- FAR, FRR, EER, DET, ROC, and minDCF.
- Metrics stratified by duration, device, noise, language, and available demographic attributes.
- Calibration and threshold selection on data separate from final evaluation.
- Anti-spoofing evaluation before authentication claims.
- Template protection, deletion, and revocation tests.
