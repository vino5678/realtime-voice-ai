import { useEffect, useRef, useState } from 'react';
import { apiUrl, deleteJob, getJob, startConversion, type Job, type ModelStatus, type Voice } from '../api/client';
import { blobToWav } from '../audio/wav';
import type { Take } from '../audio/useRecorder';
import { modelWaitMessage } from './ModelBadge';
import { SourcePicker, type AudioSource } from './SourcePicker';

type Phase = 'idle' | 'preparing' | 'converting' | 'done' | 'failed';

interface Props {
  takes: Take[];
  voices: Voice[];
  model: ModelStatus | null;
}

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));

export function ConvertSection({ takes, voices, model }: Props) {
  const [source, setSource] = useState<AudioSource | null>(null);
  const [voiceId, setVoiceId] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const run = useRef(0);

  const busy = phase === 'preparing' || phase === 'converting';
  const ready = model?.state === 'ready';
  const selectedVoice = voices.some((v) => v.id === voiceId) ? voiceId : '';
  const canConvert = ready && !busy && source !== null && selectedVoice !== '';

  useEffect(
    () => () => {
      run.current += 1;
    },
    [],
  );

  useEffect(() => {
    if (!busy) return;
    const t0 = performance.now();
    const id = window.setInterval(() => setElapsed((performance.now() - t0) / 1000), 250);
    return () => window.clearInterval(id);
  }, [busy]);

  const convert = async () => {
    if (!source || !selectedVoice) return;
    const mine = ++run.current;
    setError(null);
    setJob(null);
    setWarnings([]);
    setElapsed(0);
    setPhase('preparing');
    try {
      const prepared = await blobToWav(source.blob);
      const form = new FormData();
      form.append('voice_id', selectedVoice);
      form.append('audio', prepared.wav, 'source.wav');
      const started = await startConversion(form);
      if (run.current !== mine) return;
      setWarnings(started.warnings);
      let j = started.job;
      setJob(j);
      setPhase('converting');
      while (j.status === 'queued' || j.status === 'running') {
        await sleep(800);
        if (run.current !== mine) return;
        j = (await getJob(j.id)).job;
        setJob(j);
      }
      if (j.status === 'succeeded') {
        setPhase('done');
      } else {
        setPhase('failed');
        setError(j.error?.message ?? 'Conversion failed.');
      }
    } catch (e) {
      if (run.current !== mine) return;
      setPhase('failed');
      setError(e instanceof Error ? e.message : 'Conversion failed.');
    }
  };

  const discard = async () => {
    if (job) {
      try {
        await deleteJob(job.id);
      } catch {
        /* already expired */
      }
    }
    run.current += 1;
    setJob(null);
    setPhase('idle');
  };

  const statusText =
    phase === 'preparing'
      ? 'Preparing and uploading audio…'
      : phase === 'converting'
        ? job?.status === 'running'
          ? 'Converting on the server…'
          : 'Waiting in the queue…'
        : '';

  return (
    <section className="panel" aria-labelledby="conv-h">
      <h2 id="conv-h">Convert speech</h2>
      <p className="muted">
        Choose the speech to convert and an enrolled target voice. This converts a complete file; it is not live
        conversion.
      </p>

      <SourcePicker takes={takes} value={source} onChange={setSource} disabled={busy} />

      <label className="field">
        <span>Target voice</span>
        <select value={selectedVoice} onChange={(e) => setVoiceId(e.target.value)} disabled={busy}>
          <option value="">{voices.length === 0 ? 'Enroll a voice first' : 'Choose a target voice'}</option>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>

      <div className="controls">
        <button type="button" className="btn btn-primary" onClick={() => void convert()} disabled={!canConvert}>
          {busy ? 'Converting…' : 'Convert'}
        </button>
        {busy && (
          <span className="muted" role="status">
            {statusText} {elapsed.toFixed(0)} s
          </span>
        )}
        {!ready && <span className="muted small">{modelWaitMessage(model)}</span>}
      </div>

      {warnings.length > 0 && (
        <ul className="plain note-warn small">
          {warnings.map((w) => (
            <li key={w}>Source audio: {w}</li>
          ))}
        </ul>
      )}
      {error && (
        <p className="status status-problem" role="alert">
          {error}
        </p>
      )}

      {phase === 'done' && job && job.audio_url && (
        <div className="result">
          <div className="player">
            <p className="player-label">Original</p>
            {source && <audio controls src={source.previewUrl} preload="metadata" />}
          </div>
          <div className="player">
            <p className="player-label">Converted</p>
            <audio controls src={apiUrl(job.audio_url)} preload="metadata" />
          </div>
          <dl className="metrics">
            <div>
              <dt>Processing time</dt>
              <dd>{job.processing_seconds !== null ? `${job.processing_seconds.toFixed(2)} s` : 'unavailable'}</dd>
            </div>
            <div>
              <dt>Source length</dt>
              <dd>{job.source_seconds.toFixed(2)} s</dd>
            </div>
            <div>
              <dt>Real-time factor</dt>
              <dd>{job.rtf !== null ? job.rtf.toFixed(2) : 'unavailable'}</dd>
            </div>
            <div>
              <dt>Device</dt>
              <dd>{job.device ?? 'unknown'}</dd>
            </div>
            <div>
              <dt>Voice similarity</dt>
              <dd>not measured</dd>
            </div>
            <div>
              <dt>Engine</dt>
              <dd>{job.engine ?? 'unknown'}</dd>
            </div>
          </dl>
          <p className="muted small">
            Real-time factor is processing time divided by source length, measured for this one file. The first conversion
            after start-up may include warm-up. It does not show live-streaming latency.
          </p>
          <div className="controls">
            <a className="btn btn-primary" href={apiUrl(`${job.audio_url}?download=1`)} download="converted.wav">
              Download converted audio
            </a>
            <button type="button" className="btn btn-quiet" onClick={() => void discard()}>
              Delete result
            </button>
          </div>
          <p className="muted small">Results are kept on the server for a limited time and then deleted automatically.</p>
        </div>
      )}
    </section>
  );
}
