// Converts any browser-decodable audio (recording, MP3, M4A, WebM, WAV...) into the mono 24 kHz
// 16-bit PCM WAV the server accepts. Doing this in the browser means the server needs no ffmpeg.
export const UPLOAD_SAMPLE_RATE = 24000;

export interface PreparedAudio {
  wav: Blob;
  durationSec: number;
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const text = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i));
  };
  text(0, 'RIFF');
  v.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  text(36, 'data');
  v.setUint32(40, samples.length * 2, true);
  let o = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    o += 2;
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

export async function blobToWav(blob: Blob): Promise<PreparedAudio> {
  const ctx = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  } catch {
    throw new Error('This browser could not read that audio. Try a WAV, MP3, M4A or WebM file, or record again.');
  } finally {
    void ctx.close();
  }
  if (decoded.length === 0) throw new Error('The audio is empty.');
  const length = Math.max(1, Math.ceil(decoded.duration * UPLOAD_SAMPLE_RATE));
  const offline = new OfflineAudioContext(1, length, UPLOAD_SAMPLE_RATE);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const rendered = await offline.startRendering();
  return { wav: encodeWav(rendered.getChannelData(0), UPLOAD_SAMPLE_RATE), durationSec: rendered.duration };
}
