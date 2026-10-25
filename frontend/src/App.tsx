import { useCallback, useEffect, useRef, useState } from 'react';
import { useModelStatus, useVoices } from './api/hooks';
import { ApiStatus } from './components/ApiStatus';
import { CallSection } from './components/CallSection';
import { ConvertSection } from './components/ConvertSection';
import { ModelBadge, ModelNotice } from './components/ModelBadge';
import { VoicesSection } from './components/VoicesSection';
import { TakeCard } from './components/TakeCard';
import { Waveform } from './components/Waveform';
import { MAX_RECORD_SECONDS, useRecorder, type Take } from './audio/useRecorder';

const fmtTime = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;

export default function App() {
  const [takes, setTakes] = useState<Take[]>([]);
  const takesRef = useRef<Take[]>([]);
  takesRef.current = takes;

  const addTake = useCallback((t: Take) => setTakes((prev) => [t, ...prev]), []);
  const rec = useRecorder(addTake);
  const { status: model, offline } = useModelStatus();
  const { voices, error: voicesError, refresh } = useVoices(model !== null && !offline);

  const deleteTake = (id: string) => {
    setTakes((prev) => {
      const t = prev.find((x) => x.id === id);
      if (t) URL.revokeObjectURL(t.url);
      return prev.filter((x) => x.id !== id);
    });
  };
  const deleteAll = () => {
    takes.forEach((t) => URL.revokeObjectURL(t.url));
    setTakes([]);
  };

  // Release audio memory when the page closes.
  useEffect(
    () => () => {
      takesRef.current.forEach((t) => URL.revokeObjectURL(t.url));
    },
    [],
  );

  const live = rec.status === 'live';
  const problem = ['denied', 'no-device', 'busy', 'insecure', 'unsupported', 'error'].includes(rec.status);

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 36 36" fill="none">
              <path d="M18 7v22M12 12v12M24 12v12M7 16v4M29 16v4" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
              <circle cx="18" cy="18" r="16.5" stroke="currentColor" strokeOpacity=".22" />
            </svg>
          </span>
          <div>
            <p className="brand-kicker">VOICE WORKSPACE</p>
            <h1>Voice Bridge</h1>
          </div>
        </div>
        <div className="badges">
          <ApiStatus />
          <ModelBadge status={model} />
        </div>
      </header>

      <p className="lede">
        Record a voice sample, hear it back untouched, check its quality, then enroll an authorized target voice and convert
        speech files to it. Live (real-time) conversion is not part of this version.
      </p>

      <section className="panel scope-panel" aria-labelledby="rec-h">
        <h2 id="rec-h" className="sr-only">Recorder</h2>
        <Waveform analyser={rec.analyser} recording={rec.recording} />

        <div className="controls">
          {!live && !rec.recording && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => rec.enableMic()}
              disabled={rec.status === 'requesting'}
            >
              {rec.status === 'requesting' ? 'Waiting for permission…' : 'Enable microphone'}
            </button>
          )}

          {live && !rec.recording && (
            <>
              <button type="button" className="btn btn-record" onClick={rec.start} disabled={rec.analysing}>
                <span className="dot" aria-hidden="true" /> Record
              </button>
              <button type="button" className="btn btn-ghost" onClick={rec.disableMic}>
                Turn microphone off
              </button>
            </>
          )}

          {rec.recording && (
            <>
              <button type="button" className="btn btn-stop" onClick={rec.stop}>
                <span className="square" aria-hidden="true" /> Stop
              </button>
              <span className="timer" role="timer" aria-live="off">
                {fmtTime(rec.elapsed)} / {fmtTime(MAX_RECORD_SECONDS)}
              </span>
            </>
          )}
          {rec.analysing && <span className="muted">Checking quality…</span>}
        </div>

        {live && rec.devices.length > 0 && !rec.recording && (
          <label className="field">
            <span>Input device</span>
            <select value={rec.deviceId} onChange={(e) => rec.enableMic(e.target.value)}>
              {rec.devices.map((d, i) => (
                <option key={d.deviceId || i} value={d.deviceId}>
                  {d.label || `Microphone ${i + 1}`}
                </option>
              ))}
            </select>
          </label>
        )}

        <p className={`status${problem ? ' status-problem' : ''}`} role="status">
          {rec.message ||
            (rec.permission === 'denied'
              ? 'This site is blocked from using the microphone. Allow it in the browser address bar, then try again.'
              : 'The microphone is off.')}
        </p>
        <p className="muted small">
          Recordings stay in this browser tab and are not uploaded. Browser noise suppression, echo cancellation and
          auto-gain are switched off so the checks reflect the raw microphone signal. Use headphones if you play audio
          while recording.
        </p>
      </section>

      <aside className="consent" aria-label="Consent notice">
        <strong>Authorized voices only.</strong> Record only your own voice, or the voice of someone who has clearly
        agreed to it being recorded and used with this tool.
      </aside>

      <section aria-labelledby="takes-h" className="takes">
        <div className="takes-head">
          <h2 id="takes-h">Recordings</h2>
          {takes.length > 1 && (
            <button type="button" className="btn btn-quiet" onClick={deleteAll}>
              Delete all recordings
            </button>
          )}
        </div>
        {takes.length === 0 ? (
          <p className="empty">No recordings yet. Enable the microphone, press Record and read a few sentences aloud.</p>
        ) : (
          takes.map((t) => <TakeCard key={t.id} take={t} onDelete={deleteTake} />)
        )}
      </section>

      <ModelNotice status={model} />
      <CallSection />
      <VoicesSection takes={takes} voices={voices} voicesError={voicesError} model={model} onChanged={() => void refresh()} />
      <ConvertSection takes={takes} voices={voices} model={model} />
    </div>
  );
}
