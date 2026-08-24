import assert from "node:assert/strict";
import test from "node:test";

import { encodePcmWav, mergeFloat32 } from "../../src/voiceid/adapters/api/web/assets/audio.js";

test("mergeFloat32 preserves chunk order", () => {
  const merged = mergeFloat32([
    new Float32Array([0.1, 0.2]),
    new Float32Array([-0.3]),
  ]);
  assert.equal(merged.length, 3);
  assert.ok(Math.abs(merged[0] - 0.1) < 1e-6);
  assert.ok(Math.abs(merged[2] + 0.3) < 1e-6);
});

test("encodePcmWav creates a mono 16-bit PCM WAVE payload", async () => {
  const blob = encodePcmWav(new Float32Array([-1.2, 0, 1.2]), 48_000);
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const view = new DataView(bytes.buffer);
  const ascii = (start, length) => String.fromCharCode(...bytes.slice(start, start + length));

  assert.equal(blob.type, "audio/wav");
  assert.equal(ascii(0, 4), "RIFF");
  assert.equal(ascii(8, 4), "WAVE");
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 48_000);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getUint32(40, true), 6);
  assert.equal(view.getInt16(44, true), -32768);
  assert.equal(view.getInt16(46, true), 0);
  assert.equal(view.getInt16(48, true), 32767);
});

test("encodePcmWav rejects empty input", () => {
  assert.throws(() => encodePcmWav(new Float32Array(), 16_000), /non-empty/);
});
