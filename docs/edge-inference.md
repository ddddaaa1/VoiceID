# Edge Inference Profile

Step 13 turns the pinned SpeechBrain ECAPA model into a measurable deployment candidate. It does
not yet make the phone or a wearable a trusted biometric authenticator.

## Contract

The versioned profile is [`config/edge-profile-v1.json`](../config/edge-profile-v1.json). Its target
is a phone-class ARM64 CPU using ONNX Runtime and static INT8 QDQ inference.

| Budget | Candidate gate |
|---|---:|
| INT8 artifact | at most 32 MiB |
| Full model graph p95 | at most 150 ms |
| Product end-to-end p95 | at most 250 ms |
| Peak process working set | at most 256 MiB |
| Energy per verification | at most 1.0 J |
| Minimum FP32/INT8 embedding cosine | at least 0.98 |
| p95 absolute verification-score delta | at most 0.02 |
| Observed EER increase | at most 1 percentage point |

The model graph budget covers filter-bank features, normalization, ECAPA, and embedding
normalization. Product end-to-end latency additionally includes capture, VoiceID preprocessing,
policy, and transport. The energy and end-to-end gates cannot be evaluated on this Mac benchmark.

## Reproduce the artifacts

Install the ML and edge extras, keep the hash-locked LibriSpeech v1 corpus under `data/raw/`, and
run:

```bash
uv sync --extra ml --extra edge --extra dev
uv run --extra ml --extra edge python scripts/export_edge_ecapa.py
```

The exporter follows the current [PyTorch ONNX export contract](https://docs.pytorch.org/docs/stable/onnx_export.html)
and ONNX Runtime's [static quantization guidance](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).
It writes generated models under ignored `artifacts/edge/` and safe, non-model provenance under
`experiments/edge-ecapa-int8-v1/`.

Run the isolated ARM benchmark with:

```bash
uv run --extra edge python scripts/benchmark_edge_ecapa.py \
  artifacts/edge/ecapa-tdnn-onnx-int8-v1/manifest.json \
  --output experiments/edge-ecapa-int8-v1/arm64-benchmark.json
```

## Measured local result

The frozen report was produced on Darwin ARM64 with ONNX Runtime 1.29.0, one CPU thread, 20
evaluation-partition utterances cropped to three seconds, three warmups, and 40 timed runs.

| Measurement | FP32 | INT8 |
|---|---:|---:|
| Artifact size | 80.19 MiB | 21.25 MiB |
| Graph p95 | see frozen report | about 41 ms |
| Peak process RSS | see frozen report | about 252 MiB |

INT8 reduced artifact size by about 73.5% and passed every locally measurable candidate budget.
Across the 20-sample fidelity subset, minimum FP32/INT8 embedding cosine was about 0.9949 and p95
absolute pairwise-score delta was about 0.0163.

INT8 was slower than FP32 on this host. The result is retained because it demonstrates that
quantization is a size and memory optimization here, not a portable latency claim. Exact values,
host version, hashes, and limitations live in
[`arm64-benchmark.json`](../experiments/edge-ecapa-int8-v1/arm64-benchmark.json).

## Channel proxy evaluation

The channel experiment keeps enrollment clean, transforms probe audio only, locks the threshold on
clean INT8 development trials, and evaluates the same 120-trial LibriSpeech v2 protocol for every
condition:

```bash
uv run --extra edge python scripts/evaluate_edge_channels.py \
  artifacts/edge/ecapa-tdnn-onnx-int8-v1/manifest.json \
  experiments/librispeech-clean-v2/audio-trials.json \
  --output experiments/edge-ecapa-int8-v1/channel-proxy-report.json
```

The band-limited proxy preserved the small cohort's clean result. Additive noise at 15 dB produced
a 3.33% observed EER and 6.67% FRR at the clean threshold. Combining band limitation with 10 dB
noise produced 3.33% observed EER and 46.67% FRR at that same threshold.

These are deliberately named proxies. They are not AirPods or Ray-Ban Meta recordings. The result
supports testing channel-robust enrollment and adaptation; it does not support a wearable accuracy
claim.

## Remaining hardware gate

Step 13 is complete at the export/tooling level and remains open at the product-evidence level. It
still needs:

- iOS or Android ONNX Runtime integration with the exact artifact hash;
- p50/p95 latency and peak memory on at least one phone-class ARM device;
- device-native energy measurement for repeated and idle operation;
- consented recordings from each target wearable microphone in quiet, traffic, wind, and motion;
- cross-device enrollment/probe trials and comparison against the clean locked threshold;
- replay and modern synthetic-speech evaluation through the device capture path.
