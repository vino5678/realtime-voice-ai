import { fmtDb, type Severity } from '../audio/analysis';
import type { Take } from '../audio/useRecorder';

const LABEL: Record<Severity, string> = { good: 'Good', warn: 'Check', bad: 'Fix' };
const VERDICT: Record<Severity, string> = {
  good: 'Looks usable',
  warn: 'Usable with caveats',
  bad: 'Re-record recommended',
};

interface Props {
  take: Take;
  onDelete: (id: string) => void;
}

export function TakeCard({ take, onDelete }: Props) {
  const r = take.report;
  return (
    <article className="take">
      <header className="take-head">
        <div>
          <h3>{take.name}</h3>
          <p className="muted">
            {new Date(take.createdAt).toLocaleTimeString()}, {take.durationSec.toFixed(1)} s,{' '}
            {(take.sizeBytes / 1024).toFixed(0)} KB
          </p>
        </div>
        {r && <span className={`verdict v-${r.verdict}`}>{VERDICT[r.verdict]}</span>}
      </header>

      <div className="player">
        <p className="player-label">Original recording, no processing applied</p>
        <audio controls src={take.url} preload="metadata" />
      </div>

      {take.analysisError && <p className="note-warn">{take.analysisError}</p>}

      {r && (
        <>
          <dl className="metrics">
            <div><dt>Peak</dt><dd>{fmtDb(r.peakDb)}</dd></div>
            <div><dt>Speech level</dt><dd>{fmtDb(r.speechDb)}</dd></div>
            <div><dt>Noise floor</dt><dd>{fmtDb(r.noiseFloorDb)}</dd></div>
            <div><dt>Est. SNR</dt><dd>{r.snrDb.toFixed(0)} dB</dd></div>
            <div><dt>Clipped samples</dt><dd>{r.clippedPct.toFixed(2)}%</dd></div>
            <div><dt>Sample rate</dt><dd>{(r.sampleRate / 1000).toFixed(1)} kHz</dd></div>
          </dl>
          <ul className="findings">
            {r.findings.map((f) => (
              <li key={f.id} className={`f-${f.severity}`}>
                <span className="f-tag">{LABEL[f.severity]}</span>
                <span>
                  <strong>{f.title}.</strong> {f.detail}
                </span>
              </li>
            ))}
          </ul>
          <p className="muted small">Checks are rough screening estimates, not model-specific requirements.</p>
        </>
      )}

      <button type="button" className="btn btn-quiet" onClick={() => onDelete(take.id)}>
        Delete this recording
      </button>
    </article>
  );
}
