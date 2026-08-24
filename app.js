const state = { profile: null, active: null };
const bars = {};

for (const kind of ["enroll", "verify"]) {
  const container = document.querySelector(`#${kind}-bars`);
  bars[kind] = Array.from({ length: 42 }, () => {
    const bar = document.createElement("span");
    bar.className = "bar";
    container.appendChild(bar);
    return bar;
  });
  document.querySelector(`#${kind}-button`).addEventListener("click", () => record(kind));
}

async function record(kind) {
  if (state.active) return;
  const button = document.querySelector(`#${kind}-button`);
  const status = document.querySelector(`#${kind}-status`);

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    state.active = kind;
    button.classList.add("recording");
    button.querySelector("span:last-child").textContent = "Grabando…";
    status.textContent = "Speak now — recording ends in 5 seconds";

    const frames = [];
    const spectrum = new Uint8Array(analyser.frequencyBinCount);
    const started = performance.now();

    await new Promise((resolve) => {
      function sample(now) {
        analyser.getByteFrequencyData(spectrum);
        frames.push(summarizeSpectrum(spectrum));
        animateBars(kind, spectrum);
        if (now - started < 5000) requestAnimationFrame(sample);
        else resolve();
      }
      requestAnimationFrame(sample);
    });

    stream.getTracks().forEach((track) => track.stop());
    await context.close();
    const signature = averageFrames(frames);
    resetButton(button, kind);
    state.active = null;

    if (kind === "enroll") {
      state.profile = signature;
      status.textContent = "Acoustic profile created on this device ✓";
      const verifyCard = document.querySelector("#verify-card");
      verifyCard.classList.remove("muted");
      document.querySelector("#verify-button").disabled = false;
      document.querySelector("#verify-status").textContent = "Ready to compare";
    } else {
      showResult(similarity(state.profile, signature));
      status.textContent = "Comparison complete ✓";
    }
  } catch (error) {
    state.active = null;
    resetButton(button, kind);
    status.textContent = error.name === "NotAllowedError"
      ? "Microphone access is required"
      : "This browser could not access the microphone";
  }
}

function summarizeSpectrum(data) {
  const bins = 24;
  const result = [];
  const usable = Math.floor(data.length * 0.45);
  const size = Math.floor(usable / bins);
  for (let i = 0; i < bins; i++) {
    let sum = 0;
    for (let j = 0; j < size; j++) sum += data[i * size + j];
    result.push(sum / size / 255);
  }
  return result;
}

function averageFrames(frames) {
  return frames[0].map((_, index) =>
    frames.reduce((sum, frame) => sum + frame[index], 0) / frames.length
  );
}

function similarity(a, b) {
  const dot = a.reduce((sum, value, i) => sum + value * b[i], 0);
  const magnitudeA = Math.sqrt(a.reduce((sum, value) => sum + value ** 2, 0));
  const magnitudeB = Math.sqrt(b.reduce((sum, value) => sum + value ** 2, 0));
  const cosine = dot / (magnitudeA * magnitudeB || 1);
  return Math.max(0, Math.min(100, Math.round((cosine - 0.55) / 0.45 * 100)));
}

function animateBars(kind, spectrum) {
  bars[kind].forEach((bar, index) => {
    const value = spectrum[Math.floor(index / bars[kind].length * spectrum.length * .45)];
    bar.style.height = `${Math.max(4, value / 255 * 88)}px`;
  });
}

function resetButton(button, kind) {
  button.classList.remove("recording");
  button.querySelector("span:last-child").textContent = kind === "enroll"
    ? "Enroll again"
    : "Record another comparison";
}

function showResult(score) {
  const result = document.querySelector("#result");
  document.querySelector("#score-value").textContent = `${score}%`;
  document.querySelector("#result-title").textContent = score >= 75
    ? "The samples are highly similar"
    : score >= 50 ? "The samples share some similarities" : "The samples are different";
  document.querySelector("#result-copy").textContent =
    "This percentage describes acoustic similarity; it does not confirm a person's identity.";
  result.hidden = false;
  result.scrollIntoView({ behavior: "smooth", block: "center" });
}
