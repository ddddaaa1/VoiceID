# ECAPA INT8 Edge Candidate v1

This experiment freezes non-audio evidence for the first full-waveform VoiceID edge candidate.

- `artifact-provenance.json` binds generated FP32 and INT8 files to hashes, source revision,
  calibration manifest, quantization settings, and toolchain. The large model files are generated
  locally and are not committed.
- `arm64-benchmark.json` records isolated single-thread latency, process peak RSS, size, and
  embedding/score fidelity on one Darwin ARM64 host.
- `channel-proxy-report.json` records aggregate biometric metrics for clean, band-limited, and noisy
  probes. It publishes neither raw audio nor per-trial biometric scores.

The artifact is an experimental deployment candidate. Phone performance, energy consumption, and
target wearable microphones remain unmeasured.
