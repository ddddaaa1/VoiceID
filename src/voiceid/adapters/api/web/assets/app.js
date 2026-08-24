import { encodePcmWav, mergeFloat32 } from "/assets/audio.js";

const RECORDING_SECONDS = 5;
const REQUIRED_ENROLLMENT_SAMPLES = 3;
const IDENTITY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const state = {
  active: null,
  enrollmentSamples: [],
  enrolled: false,
  template: null,
};

const elements = {
  apiStatus: document.querySelector("#api-status"),
  identityId: document.querySelector("#identity-id"),
  enrollCard: document.querySelector("#enroll-card"),
  enrollRecordButton: document.querySelector("#enroll-record-button"),
  enrollSubmitButton: document.querySelector("#enroll-submit-button"),
  enrollResetButton: document.querySelector("#enroll-reset-button"),
  enrollStatus: document.querySelector("#enroll-status"),
  sampleProgress: document.querySelector("#sample-progress"),
  verifyCard: document.querySelector("#verify-card"),
  verifyButton: document.querySelector("#verify-button"),
  verifyStatus: document.querySelector("#verify-status"),
  result: document.querySelector("#result"),
};

const bars = Object.fromEntries(
  ["enroll", "verify"].map((kind) => {
    const container = document.querySelector(`#${kind}-bars`);
    const created = Array.from({ length: 42 }, () => {
      const bar = document.createElement("span");
      bar.className = "bar";
      container.appendChild(bar);
      return bar;
    });
    return [kind, created];
  }),
);

elements.enrollRecordButton.addEventListener("click", recordEnrollmentSample);
elements.enrollSubmitButton.addEventListener("click", submitEnrollment);
elements.enrollResetButton.addEventListener("click", resetEnrollment);
elements.verifyButton.addEventListener("click", verifyIdentity);
elements.identityId.addEventListener("input", validateIdentity);

checkApiHealth();

async function checkApiHealth() {
  try {
    const response = await fetch("/api/v1/health", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Health check returned ${response.status}`);
    const health = await response.json();
    elements.apiStatus.textContent = `● API ready · ${shortModelName(health.speaker_model_id)}`;
    elements.apiStatus.className = "api-pill online";
    elements.apiStatus.title = `Policy: ${health.verification_policy_id}; persistence: ${health.persistence}`;
  } catch {
    elements.apiStatus.textContent = "● API unavailable";
    elements.apiStatus.className = "api-pill offline";
  }
}

async function recordEnrollmentSample() {
  if (state.enrollmentSamples.length >= REQUIRED_ENROLLMENT_SAMPLES) return;
  const sampleNumber = state.enrollmentSamples.length + 1;
  try {
    const blob = await captureWav("enroll", (secondsLeft) => {
      setStatus(elements.enrollStatus, `Recording sample ${sampleNumber} · ${secondsLeft}s remaining`);
    });
    state.enrollmentSamples.push(blob);
    updateEnrollmentControls();
    setStatus(elements.enrollStatus, `Sample ${sampleNumber} captured ✓`, "success");
  } catch (error) {
    showCaptureError(elements.enrollStatus, error);
  }
}

async function submitEnrollment() {
  const identityId = readIdentity();
  if (!identityId || state.enrollmentSamples.length !== REQUIRED_ENROLLMENT_SAMPLES) return;

  setBusy(elements.enrollSubmitButton, true, "Building ECAPA template…");
  setStatus(elements.enrollStatus, "Validating audio and generating speaker embeddings…");
  const form = new FormData();
  state.enrollmentSamples.forEach((sample, index) => {
    form.append("samples", sample, `enrollment-${index + 1}.wav`);
  });

  try {
    const template = await requestJson(
      `/api/v1/identities/${encodeURIComponent(identityId)}/enroll`,
      { method: "POST", body: form },
    );
    state.enrolled = true;
    state.template = template;
    elements.identityId.disabled = true;
    elements.enrollRecordButton.disabled = true;
    elements.enrollSubmitButton.disabled = true;
    elements.enrollResetButton.disabled = false;
    elements.verifyCard.classList.remove("muted");
    elements.verifyButton.disabled = false;
    setStatus(
      elements.enrollStatus,
      `Profile v${template.template_version} created from ${template.retained_samples} samples ✓`,
      "success",
    );
    setStatus(elements.verifyStatus, "Ready for a fresh verification sample");
  } catch (error) {
    setStatus(elements.enrollStatus, error.message, "error");
  } finally {
    setBusy(elements.enrollSubmitButton, false, "Create voice profile");
    if (state.enrolled) elements.enrollSubmitButton.disabled = true;
  }
}

async function verifyIdentity() {
  if (!state.enrolled) return;
  elements.result.hidden = true;
  try {
    const blob = await captureWav("verify", (secondsLeft) => {
      setStatus(elements.verifyStatus, `Recording probe · ${secondsLeft}s remaining`);
    });
    setBusy(elements.verifyButton, true, "Comparing speaker embedding…");
    setStatus(elements.verifyStatus, "Running the verification policy…");
    const form = new FormData();
    form.append("sample", blob, "verification.wav");
    const result = await requestJson(
      `/api/v1/identities/${encodeURIComponent(elements.identityId.value)}/verify`,
      { method: "POST", body: form },
    );
    showVerificationResult(result);
    setStatus(elements.verifyStatus, "Verification complete ✓", "success");
  } catch (error) {
    showCaptureError(elements.verifyStatus, error);
  } finally {
    setBusy(elements.verifyButton, false, "Record another verification");
  }
}

async function captureWav(kind, onProgress) {
  if (state.active) throw new Error("Another recording is already in progress.");
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
    throw new Error("This browser does not support the required audio recording APIs.");
  }

  state.active = kind;
  const button = kind === "enroll" ? elements.enrollRecordButton : elements.verifyButton;
  setRecordingState(button, true);

  let stream;
  let context;
  let animationFrame;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    context = new AudioContext();
    await context.audioWorklet.addModule("/assets/audio-recorder-worklet.js");
    await context.resume();

    const source = context.createMediaStreamSource(stream);
    const recorder = new AudioWorkletNode(context, "pcm-recorder");
    const analyser = context.createAnalyser();
    const silentOutput = context.createGain();
    const chunks = [];
    analyser.fftSize = 2048;
    silentOutput.gain.value = 0;
    recorder.port.onmessage = ({ data }) => chunks.push(new Float32Array(data));
    source.connect(analyser);
    source.connect(recorder);
    recorder.connect(silentOutput).connect(context.destination);

    const startedAt = performance.now();
    const spectrum = new Uint8Array(analyser.frequencyBinCount);
    await new Promise((resolve) => {
      const update = (now) => {
        const elapsed = now - startedAt;
        analyser.getByteFrequencyData(spectrum);
        animateBars(kind, spectrum);
        onProgress(Math.max(1, Math.ceil(RECORDING_SECONDS - elapsed / 1000)));
        if (elapsed < RECORDING_SECONDS * 1000) {
          animationFrame = requestAnimationFrame(update);
        } else {
          resolve();
        }
      };
      animationFrame = requestAnimationFrame(update);
    });

    recorder.port.onmessage = null;
    source.disconnect();
    recorder.disconnect();
    analyser.disconnect();
    silentOutput.disconnect();
    const samples = mergeFloat32(chunks);
    return encodePcmWav(samples, context.sampleRate);
  } finally {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    stream?.getTracks().forEach((track) => track.stop());
    if (context && context.state !== "closed") await context.close();
    state.active = null;
    setRecordingState(button, false);
    resetBars(kind);
  }
}

async function requestJson(url, options) {
  let response;
  try {
    response = await fetch(url, { ...options, headers: { Accept: "application/json" } });
  } catch {
    throw new Error("The VoiceID API could not be reached.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    const details = Array.isArray(error?.details)
      ? ` (${error.details.map(formatSampleIssue).join("; ")})`
      : "";
    throw new Error(`${error?.message || `Request failed with status ${response.status}`}${details}`);
  }
  return body;
}

function updateEnrollmentControls() {
  const count = state.enrollmentSamples.length;
  [...elements.sampleProgress.children].forEach((item, index) => {
    item.classList.toggle("complete", index < count);
  });
  elements.enrollResetButton.disabled = count === 0;
  elements.enrollSubmitButton.disabled = count !== REQUIRED_ENROLLMENT_SAMPLES;
  elements.enrollRecordButton.disabled = count >= REQUIRED_ENROLLMENT_SAMPLES;
  elements.enrollRecordButton.querySelector("span:last-child").textContent =
    count < REQUIRED_ENROLLMENT_SAMPLES ? `Record sample ${count + 1}` : "All samples captured";
}

function resetEnrollment() {
  state.enrollmentSamples = [];
  state.enrolled = false;
  state.template = null;
  elements.identityId.disabled = false;
  elements.verifyCard.classList.add("muted");
  elements.verifyButton.disabled = true;
  elements.result.hidden = true;
  updateEnrollmentControls();
  setStatus(elements.enrollStatus, "Three samples are required");
  setStatus(elements.verifyStatus, "Create the voice profile first");
}

function validateIdentity() {
  const valid = IDENTITY_PATTERN.test(elements.identityId.value.trim());
  elements.identityId.setCustomValidity(
    valid ? "" : "Use letters, numbers, dots, underscores, colons, or hyphens.",
  );
  return valid;
}

function readIdentity() {
  if (!validateIdentity() || !elements.identityId.reportValidity()) return null;
  return elements.identityId.value.trim();
}

function showVerificationResult(result) {
  const badge = document.querySelector("#decision-badge");
  badge.textContent = result.decision.toUpperCase();
  badge.className = `decision-badge ${result.decision}`;
  document.querySelector("#result-title").textContent = decisionTitle(result.decision);
  document.querySelector("#result-copy").textContent =
    "This is an experimental model decision, not proof of identity or liveness.";
  document.querySelector("#score-value").textContent =
    result.speaker_score == null ? "N/A" : result.speaker_score.toFixed(3);
  document.querySelector("#policy-value").textContent = result.policy_id;
  document.querySelector("#template-value").textContent = `v${result.template_version} · ${shortId(result.template_id)}`;
  document.querySelector("#reasons-value").textContent = result.reasons
    .map((reason) => reason.replaceAll("_", " "))
    .join(", ");
  elements.result.hidden = false;
  elements.result.scrollIntoView({ behavior: "smooth", block: "center" });
}

function animateBars(kind, spectrum) {
  bars[kind].forEach((bar, index) => {
    const bin = Math.floor((index / bars[kind].length) * spectrum.length * 0.45);
    bar.style.height = `${Math.max(4, (spectrum[bin] / 255) * 88)}px`;
  });
}

function resetBars(kind) {
  bars[kind].forEach((bar) => { bar.style.height = "4px"; });
}

function setRecordingState(button, recording) {
  button.classList.toggle("recording", recording);
  button.disabled = recording;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.classList.toggle("busy", busy);
  const labelElement = button.querySelector("span:last-child");
  if (labelElement) labelElement.textContent = label;
  else button.textContent = label;
}

function setStatus(element, message, tone = "") {
  element.textContent = message;
  element.dataset.tone = tone;
}

function showCaptureError(status, error) {
  const message = error?.name === "NotAllowedError"
    ? "Microphone permission is required to record a sample."
    : error?.message || "The microphone could not be accessed.";
  setStatus(status, message, "error");
}

function formatSampleIssue(issue) {
  const reasons = issue.reasons?.join(", ") || "invalid sample";
  return `sample ${Number(issue.sample_index) + 1}: ${reasons}`;
}

function decisionTitle(decision) {
  return {
    accept: "Speaker similarity met the policy",
    reject: "Speaker similarity did not meet the policy",
    review: "The result requires review",
  }[decision] || "Verification complete";
}

function shortModelName(modelId) {
  return modelId.split("/").at(-1) || modelId;
}

function shortId(value) {
  return value.length > 14 ? `${value.slice(0, 8)}…` : value;
}
