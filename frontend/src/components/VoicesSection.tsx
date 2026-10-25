import { useState } from 'react';
import { CONSENT_STATEMENT, deleteVoice, enrollVoice, type ModelStatus, type Voice } from '../api/client';
import { blobToWav } from '../audio/wav';
import type { Take } from '../audio/useRecorder';
import { modelWaitMessage } from './ModelBadge';
import { SourcePicker, type AudioSource } from './SourcePicker';

type Mode = 'quick' | 'hq';

interface Props {
  takes: Take[];
  voices: Voice[];
  voicesError: string | null;
  model: ModelStatus | null;
  onChanged: () => void;
}

const GUIDE: Record<Mode, string> = {
  quick:
    'Use 5 to 15 seconds of natural speech from one speaker in a quiet room (3 to 30 seconds accepted). The server builds a speaker embedding from this single clip.',
  hq: 'Use a longer recording (20 seconds to 5 minutes): read several different sentences naturally at a steady distance from the microphone, with no music or background voices. The server cuts it into clips for the model. A longer recording does not automatically give a better result, so compare both modes on your own voice.',
};

export function VoicesSection({ takes, voices, voicesError, model, onChanged }: Props) {
  const [mode, setMode] = useState<Mode>('quick');
  const [name, setName] = useState('');
  const [consent, setConsent] = useState(false);
  const [source, setSource] = useState<AudioSource | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string; warnings?: string[] } | null>(null);

  const ready = model?.state === 'ready';
  const canEnroll = ready && !busy && consent && name.trim().length > 0 && source !== null;

  const enroll = async () => {
    if (!source) return;
    setBusy(true);
    setMessage(null);
    try {
      const prepared = await blobToWav(source.blob);
      const form = new FormData();
      form.append('name', name.trim());
      form.append('mode', mode);
      form.append('consent', 'true');
      form.append('audio', prepared.wav, 'reference.wav');
      const res = await enrollVoice(form);
      setMessage({
        ok: true,
        text: `Voice "${res.voice.name}" enrolled from ${res.voice.reference_seconds.toFixed(1)} s of audio in ${res.voice.segments} clip(s).`,
        warnings: res.voice.warnings,
      });
      setName('');
      setConsent(false);
      onChanged();
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : 'Enrollment failed.' });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (v: Voice) => {
    if (!window.confirm(`Delete the voice profile "${v.name}"? This cannot be undone.`)) return;
    try {
      await deleteVoice(v.id);
      onChanged();
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : 'Could not delete the voice.' });
    }
  };

  return (
    <section className="panel" aria-labelledby="voice-h">
      <h2 id="voice-h">Target voice</h2>
      <p className="muted">
        Enroll the voice you want converted speech to sound like. Only enroll your own voice, or a voice whose owner has
        given you explicit permission.
      </p>

      <div className="seg" role="group" aria-label="Enrollment type">
        <button type="button" className={mode === 'quick' ? 'on' : ''} aria-pressed={mode === 'quick'} onClick={() => setMode('quick')} disabled={busy}>
          Quick enrollment
        </button>
        <button type="button" className={mode === 'hq' ? 'on' : ''} aria-pressed={mode === 'hq'} onClick={() => setMode('hq')} disabled={busy}>
          High-quality enrollment
        </button>
      </div>
      <p className="muted small">{GUIDE[mode]}</p>

      <label className="field">
        <span>Voice name</span>
        <input className="input" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="For example: My voice" disabled={busy} />
      </label>

      <SourcePicker takes={takes} value={source} onChange={setSource} disabled={busy} />

      <label className="checkline">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} disabled={busy} />
        <span>{CONSENT_STATEMENT}</span>
      </label>

      <div className="controls">
        <button type="button" className="btn btn-primary" onClick={() => void enroll()} disabled={!canEnroll}>
          {busy ? 'Enrolling…' : 'Enroll voice'}
        </button>
        {!ready && <span className="muted small">{modelWaitMessage(model)}</span>}
      </div>

      {message && (
        <div className={`status${message.ok ? '' : ' status-problem'}`} role="status">
          <p>{message.text}</p>
          {message.warnings && message.warnings.length > 0 && (
            <ul className="plain">
              {message.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <h3 className="sub">Enrolled voices</h3>
      {voicesError && <p className="status status-problem">{voicesError}</p>}
      {voices.length === 0 ? (
        <p className="empty">No voices enrolled yet.</p>
      ) : (
        <ul className="plain voice-list">
          {voices.map((v) => (
            <li key={v.id} className="voice-item">
              <div>
                <strong>{v.name}</strong>
                <p className="muted small">
                  {v.mode === 'hq' ? 'High-quality' : 'Quick'} enrollment, {v.reference_seconds.toFixed(1)} s of reference audio, {v.segments} clip(s),
                  created {new Date(v.created_at).toLocaleString()}
                </p>
                <p className="muted small">{v.artifact}</p>
                {v.warnings.length > 0 && <p className="note-warn small">{v.warnings.join(' ')}</p>}
              </div>
              <button type="button" className="btn btn-quiet" onClick={() => void remove(v)}>
                Delete voice
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
