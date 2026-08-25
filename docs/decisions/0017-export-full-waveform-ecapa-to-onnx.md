# ADR 0017: Export Full-waveform ECAPA as Static INT8 ONNX

- Status: Accepted
- Date: 2026-08-26

## Context

The server adapter loads SpeechBrain and PyTorch, computes filter-bank features, runs ECAPA-TDNN,
and returns a 192-dimensional speaker embedding. That stack is useful for research but is too large
and too framework-specific to be the final runtime contract for a phone companion. Exporting only
the ECAPA core would leave an undocumented feature-extraction dependency and could produce
different embeddings on the device.

Quantization can reduce artifact and working-set size, but its speed and accuracy effects depend on
the target backend. A desktop ARM result cannot be presented as evidence from a phone, AirPods, or
Ray-Ban Meta.

## Decision

Export one dynamic-length ONNX graph containing the SpeechBrain filter-bank frontend, input
normalization, ECAPA-TDNN encoder, and final L2 normalization. The graph accepts one mono float32
waveform at 16 kHz and produces one normalized 192-dimensional embedding.

Create an FP32 reference artifact and a static INT8 QDQ candidate. Quantize convolution operators
with uint8 activations, int8 per-channel weights, MinMax calibration, and hash-verified samples from
the LibriSpeech development partition. Bind both generated files, the calibration manifest, the
upstream model revision, and the toolchain to SHA-256 provenance. Keep the large generated binaries
outside Git; publish aggregate evidence and exact hashes in the repository.

Require a direct PyTorch-to-FP32-ONNX cosine of at least 0.9999 and a PyTorch-to-INT8 cosine of at
least 0.98 during export. Benchmark each ONNX variant in a fresh, single-threaded process. Report
process peak RSS rather than Python-only allocations.

Treat software band limiting and additive noise as channel proxies only. A Step 13 hardware gate
remains open until the same artifact is measured on phone-class ARM hardware and evaluated with
recordings captured from target wearable microphones. Energy requires device-native tooling.

## Consequences

The edge boundary now includes feature extraction and can be implemented by any ONNX Runtime
client without SpeechBrain. Integrity checks prevent silently substituting a different graph.

The INT8 artifact is materially smaller, but it is not automatically faster on every CPU. Static
calibration and the current small speech cohort do not establish production accuracy. The project
must not enable edge decisions or make wearable performance claims solely from this evidence.
