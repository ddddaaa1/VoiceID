# VoiceID Web Workflow

The web client is a dependency-free ES module application served by the FastAPI process. It is a thin adapter: audio capture and presentation happen in the browser, while preprocessing, embeddings, template construction, scoring, and decisions remain in the Python application.

## User flow

1. The client checks `GET /api/v1/health` and displays the active speaker model.
2. The user chooses a caller-defined identity identifier.
3. An `AudioWorklet` captures three five-second mono recordings as floating-point frames.
4. The client encodes each recording as a 16-bit PCM WAVE file and submits them as the repeated `samples` multipart field.
5. A successful enrollment locks the identity and enables verification.
6. A fresh recording is submitted as the `sample` multipart field.
7. The result shows the raw cosine score, policy version, template version, decision, and auditable reason codes.

The interface never creates its own biometric decision. It presents the API response without converting the cosine score into an invented percentage.

## Browser audio boundary

`src/voiceid/adapters/api/web/assets/audio-recorder-worklet.js` copies microphone frames off the real-time audio thread. `audio.js` merges the frames and creates a mono PCM WAVE payload using the browser audio context's native sample rate. The backend remains responsible for defensive decoding, conversion to 16 kHz, VAD, and quality checks.

The capture implementation connects the worklet to a zero-gain output node so browsers continue processing audio without playing microphone feedback. Tracks, audio nodes, animation frames, and the audio context are closed after every capture, including failures.

## State and failure handling

The UI enables profile creation only after exactly three local samples are present and enables verification only after the API confirms enrollment. Expected API errors use the stable error envelope and are rendered as human-readable status text. Reloading the page resets client state; restarting the server also removes templates because persistence is currently in memory.

## Security and privacy posture

- The web client and API share an origin; no permissive CORS configuration is required.
- Static responses use a restrictive Content Security Policy, `nosniff`, a no-referrer policy, and a same-origin microphone permissions policy.
- Raw recordings are sent to the local API and are not intentionally persisted. Multipart handling may temporarily spool request data.
- Voice templates are sensitive biometric data even though raw audio is not stored.
- Anti-spoofing, authentication, rate limiting, encrypted persistence, consent, and retention controls are not implemented yet.

## Automated coverage

Python API contract tests verify that the page and recording assets are served with their security headers. Node tests validate chunk ordering, PCM WAVE headers, sample rate, bit depth, data size, and clipping. Manual browser validation checks the integrated page, API health state, and responsive layout without granting microphone permission automatically.
