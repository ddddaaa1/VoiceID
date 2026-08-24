const PCM_MAX = 32767;
const PCM_MIN = -32768;

export function mergeFloat32(chunks) {
  const totalLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export function encodePcmWav(samples, sampleRate) {
  if (!(samples instanceof Float32Array) || samples.length === 0) {
    throw new TypeError("samples must be a non-empty Float32Array");
  }
  if (!Number.isInteger(sampleRate) || sampleRate <= 0) {
    throw new TypeError("sampleRate must be a positive integer");
  }

  const headerBytes = 44;
  const bytesPerSample = 2;
  const dataBytes = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(headerBytes + dataBytes);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);

  samples.forEach((sample, index) => {
    const clipped = Math.max(-1, Math.min(1, sample));
    const pcm = clipped < 0 ? clipped * -PCM_MIN : clipped * PCM_MAX;
    view.setInt16(headerBytes + index * bytesPerSample, Math.round(pcm), true);
  });

  return new Blob([buffer], { type: "audio/wav" });
}

function writeAscii(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}
