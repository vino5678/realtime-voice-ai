import { useCallback, useEffect, useRef, useState } from 'react';
import { analyzeBuffer, type QualityReport } from './analysis';

export interface Take {
  id: string;
  name: string;
  createdAt: number;
  url: string;
  sizeBytes: number;
  mimeType: string;
  durationSec: number;
  report: QualityReport | null;
  analysisError: string | null;
}

export type MicStatus =
  | 'off'
  | 'requesting'
  | 'live'
  | 'denied'
  | 'no-device'
  | 'busy'
  | 'insecure'
  | 'unsupported'
  | 'error';

export type PermissionHint = 'unknown' | 'prompt' | 'granted' | 'denied';

export const MAX_RECORD_SECONDS = 60;

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];

function pickMimeType(): string {
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) ?? '';
}

function describeError(e: unknown): { status: MicStatus; message: string } {
  const name = (e as { name?: string } | null)?.name ?? '';
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return {
        status: 'denied',
        message: 'Microphone access is blocked. Allow it from the lock icon in the address bar, then press Enable microphone.',
      };
    case 'NotFoundError':
    case 'OverconstrainedError':
      return { status: 'no-device', message: 'No microphone was found. Connect one or choose a different input.' };
    case 'NotReadableError':
    case 'AbortError':
      return {
        status: 'busy',
        message: 'The microphone could not be opened. Close other apps that may be using it and try again.',
      };
    default:
      return { status: 'error', message: e instanceof Error ? e.message : 'Could not open the microphone.' };
  }
}

export function useRecorder(onTake: (take: Take) => void) {
  const [status, setStatus] = useState<MicStatus>('off');
  const [message, setMessage] = useState('');
  const [permission, setPermission] = useState<PermissionHint>('unknown');
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState('');
  const [recording, setRecording] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const countRef = useRef(0);
  const onTakeRef = useRef(onTake);
  onTakeRef.current = onTake;

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const teardown = useCallback(() => {
    clearTimer();
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.onstop = null; // discard in-progress audio when the mic goes away
      try {
        rec.stop();
      } catch {
        /* already stopped */
      }
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((t) => {
      t.onended = null;
      t.onmute = null;
      t.onunmute = null;
      t.stop();
    });
    streamRef.current = null;
    void ctxRef.current?.close();
    ctxRef.current = null;
    setAnalyser(null);
    setRecording(false);
  }, []);

  // Permission hint (Permissions API is not available everywhere, e.g. some Safari versions).
  useEffect(() => {
    let perm: PermissionStatus | null = null;
    const sync = () => {
      if (perm) setPermission(perm.state as PermissionHint);
    };
    navigator.permissions
      ?.query({ name: 'microphone' as PermissionName })
      .then((s) => {
        perm = s;
        sync();
        s.onchange = sync;
      })
      .catch(() => setPermission('unknown'));
    return () => {
      if (perm) perm.onchange = null;
    };
  }, []);

  // Keep the device list fresh when hardware is plugged in or removed.
  useEffect(() => {
    if (status !== 'live') return;
    const refresh = () =>
      navigator.mediaDevices
        .enumerateDevices()
        .then((all) => setDevices(all.filter((d) => d.kind === 'audioinput')))
        .catch(() => undefined);
    navigator.mediaDevices.addEventListener('devicechange', refresh);
    return () => navigator.mediaDevices.removeEventListener('devicechange', refresh);
  }, [status]);

  useEffect(() => teardown, [teardown]);

  const enableMic = useCallback(
    async (id?: string) => {
      if (!window.isSecureContext) {
        setStatus('insecure');
        setMessage('Microphone access needs a secure page. Open the app at http://localhost:5173 or over HTTPS.');
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        setStatus('unsupported');
        setMessage('This browser cannot record audio. Use a current version of Chrome, Edge, Firefox or Safari.');
        return;
      }
      teardown();
      setStatus('requesting');
      setMessage('Waiting for you to allow microphone access.');
      let stream: MediaStream | null = null;
      let ctx: AudioContext | null = null;
      try {
        // Processing is off on purpose: enrollment needs the raw signal, and the
        // quality checks should reflect what the microphone actually captured.
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            deviceId: id ? { exact: id } : undefined,
            channelCount: 1,
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          },
        });
        ctx = new AudioContext();
        await ctx.resume();
        const node = ctx.createAnalyser();
        node.fftSize = 2048;
        ctx.createMediaStreamSource(stream).connect(node);

        const track = stream.getAudioTracks()[0];
        track.onmute = () => {
          setMessage('Microphone input was interrupted by the browser or device. Check the microphone, then reconnect it if needed.');
        };
        track.onunmute = () => setMessage(track.label || 'Microphone ready');
        track.onended = () => {
          teardown();
          setStatus('error');
          setMessage('The microphone was disconnected. Press Enable microphone to reconnect.');
        };
        streamRef.current = stream;
        ctxRef.current = ctx;
        setAnalyser(node);

        const all = await navigator.mediaDevices.enumerateDevices();
        setDevices(all.filter((d) => d.kind === 'audioinput'));
        setDeviceId(track.getSettings().deviceId ?? id ?? '');
        setStatus('live');
        setMessage(track.label || 'Microphone ready');
      } catch (e) {
        stream?.getTracks().forEach((track) => {
          track.onended = null;
          track.onmute = null;
          track.onunmute = null;
          track.stop();
        });
        if (streamRef.current === stream) streamRef.current = null;
        if (ctxRef.current === ctx) ctxRef.current = null;
        if (ctx && ctx.state !== 'closed') void ctx.close();
        setAnalyser(null);
        const d = describeError(e);
        setStatus(d.status);
        setMessage(d.message);
      }
    },
    [teardown],
  );

  const disableMic = useCallback(() => {
    teardown();
    setStatus('off');
    setMessage('');
  }, [teardown]);

  const stop = useCallback(() => {
    clearTimer();
    const rec = recorderRef.current;
    if (rec && rec.state !== 'inactive') rec.stop();
    setRecording(false);
  }, []);

  const start = useCallback(() => {
    const stream = streamRef.current;
    if (!stream || recorderRef.current) return;
    const mimeType = pickMimeType();
    let rec: MediaRecorder;
    try {
      rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (e) {
      setStatus('error');
      setMessage(`Could not start recording: ${e instanceof Error ? e.message : 'unknown error'}`);
      return;
    }
    chunksRef.current = [];
    rec.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    rec.onstop = async () => {
      recorderRef.current = null;
      const type = rec.mimeType || mimeType || 'audio/webm';
      const blob = new Blob(chunksRef.current, { type });
      chunksRef.current = [];
      let durationSec = (performance.now() - startedAtRef.current) / 1000;
      let report: QualityReport | null = null;
      let analysisError: string | null = null;

      setAnalysing(true);
      try {
        const ctx = new AudioContext();
        try {
          const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
          report = analyzeBuffer(buf);
          durationSec = buf.duration;
        } finally {
          void ctx.close();
        }
      } catch {
        analysisError = 'This browser could not decode the recording for analysis. Playback may still work.';
      }
      countRef.current += 1;
      onTakeRef.current({
        id: crypto.randomUUID(),
        name: `Take ${countRef.current}`,
        createdAt: Date.now(),
        url: URL.createObjectURL(blob),
        sizeBytes: blob.size,
        mimeType: type,
        durationSec,
        report,
        analysisError,
      });
      setAnalysing(false);
    };
    rec.start(250);
    recorderRef.current = rec;
    startedAtRef.current = performance.now();
    setElapsed(0);
    setRecording(true);
    timerRef.current = window.setInterval(() => {
      const s = (performance.now() - startedAtRef.current) / 1000;
      setElapsed(s);
      if (s >= MAX_RECORD_SECONDS) stop();
    }, 100);
  }, [stop]);

  return { status, message, permission, devices, deviceId, recording, analysing, elapsed, analyser, enableMic, disableMic, start, stop };
}
