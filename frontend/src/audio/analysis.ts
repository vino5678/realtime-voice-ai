// Heuristic recording-quality checks. These are rough screening thresholds,
// NOT model requirements. They will be tuned once a voice-conversion model is chosen (Phase 2).

export type Severity = 'good' | 'warn' | 'bad';

export interface Finding {
  id: string;
  severity: Severity;
  title: string;
  detail: string;
}

export interface QualityReport {
  durationSec: number;
  sampleRate: number;
  peakDb: number;
  speechDb: number;
  noiseFloorDb: number;
  snrDb: number;
  clippedPct: number;
  verdict: Severity;
  findings: Finding[];
}

const toDb = (x: number) => 20 * Math.log10(Math.max(x, 1e-9));

function percentile(sortedAsc: number[], p: number): number {
  if (sortedAsc.length === 0) return -120;
  const i = Math.min(sortedAsc.length - 1, Math.max(0, Math.round(p * (sortedAsc.length - 1))));
  return sortedAsc[i];
}

export function analyzeBuffer(buf: AudioBuffer): QualityReport {
  const sr = buf.sampleRate;
  const channels = buf.numberOfChannels;
  const n = buf.length;

  // Mix down to mono for analysis only.
  const mono = new Float32Array(n);
  for (let c = 0; c < channels; c++) {
    const data = buf.getChannelData(c);
    for (let i = 0; i < n; i++) mono[i] += data[i] / channels;
  }

  let peak = 0;
  let clipped = 0;
  for (let i = 0; i < n; i++) {
    const a = Math.abs(mono[i]);
    if (a > peak) peak = a;
    if (a >= 0.999) clipped++;
  }

  // 20 ms frame RMS levels in dBFS.
  const frameLen = Math.max(1, Math.round(sr * 0.02));
  const frameDbs: number[] = [];
  for (let start = 0; start + frameLen <= n; start += frameLen) {
    let sum = 0;
    for (let i = start; i < start + frameLen; i++) sum += mono[i] * mono[i];
    frameDbs.push(toDb(Math.sqrt(sum / frameLen)));
  }
  frameDbs.sort((a, b) => a - b);

  const noiseFloorDb = percentile(frameDbs, 0.1);
  const speechDb = percentile(frameDbs, 0.9);
  const snrDb = speechDb - noiseFloorDb;
  const peakDb = toDb(peak);
  const clippedPct = n > 0 ? (clipped / n) * 100 : 0;
  const durationSec = buf.duration;

  const findings: Finding[] = [];
  const add = (id: string, severity: Severity, title: string, detail: string) =>
    findings.push({ id, severity, title, detail });

  // Duration
  if (durationSec < 2) add('duration', 'bad', 'Too short', 'Record at least a few seconds of continuous speech.');
  else if (durationSec < 5) add('duration', 'warn', 'Short recording', 'Longer samples (5 seconds or more) usually give the model more to work with.');
  else add('duration', 'good', 'Length is fine', `${durationSec.toFixed(1)} seconds recorded.`);

  // Signal present?
  if (speechDb < -60) {
    add('level', 'bad', 'No signal detected', 'The recording is almost silent. Check that the right microphone is selected and not muted.');
  } else if (speechDb < -40) {
    add('level', 'bad', 'Far too quiet', 'Move closer to the microphone or raise its input level in Windows sound settings.');
  } else if (speechDb < -32) {
    add('level', 'warn', 'Quiet', 'Speak a little louder or move closer to the microphone.');
  } else if (speechDb > -6) {
    add('level', 'warn', 'Very loud', 'Move back from the microphone or lower its input level.');
  } else {
    add('level', 'good', 'Level is good', 'Speech level sits in a healthy range.');
  }

  // Clipping
  if (clippedPct > 0.5 || (peakDb > -0.1 && clippedPct > 0.1)) {
    add('clipping', 'bad', 'Clipping', 'The signal hit the maximum level and is distorted. Lower the input level and record again.');
  } else if (clippedPct > 0.05 || peakDb > -1) {
    add('clipping', 'warn', 'Close to clipping', 'Peaks are very near the maximum. Lower the input level a little.');
  } else {
    add('clipping', 'good', 'No clipping', `Peak level ${peakDb.toFixed(1)} dBFS.`);
  }

  // Noise
  if (speechDb >= -60) {
    if (noiseFloorDb > -40) add('noise', 'bad', 'Noisy', 'Background noise is high. Find a quieter room and turn off fans or music.');
    else if (noiseFloorDb > -50) add('noise', 'warn', 'Some background noise', 'A quieter room would improve results.');
    else add('noise', 'good', 'Quiet background', `Noise floor about ${noiseFloorDb.toFixed(0)} dBFS.`);

    if (snrDb < 15) add('snr', 'bad', 'Speech barely stands out', `Estimated signal-to-noise ratio is ${snrDb.toFixed(0)} dB.`);
    else if (snrDb < 25) add('snr', 'warn', 'Moderate signal-to-noise ratio', `Estimated ${snrDb.toFixed(0)} dB. More than 25 dB is better.`);
    else add('snr', 'good', 'Clear speech', `Estimated signal-to-noise ratio ${snrDb.toFixed(0)} dB.`);
  }

  const rank: Record<Severity, number> = { good: 0, warn: 1, bad: 2 };
  const verdict = findings.reduce<Severity>((w, f) => (rank[f.severity] > rank[w] ? f.severity : w), 'good');

  return { durationSec, sampleRate: sr, peakDb, speechDb, noiseFloorDb, snrDb, clippedPct, verdict, findings };
}

export const fmtDb = (n: number) => (Number.isFinite(n) && n > -100 ? `${n.toFixed(1)} dBFS` : 'n/a');
