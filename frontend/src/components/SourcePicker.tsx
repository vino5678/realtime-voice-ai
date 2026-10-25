import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import type { Take } from '../audio/useRecorder';

export interface AudioSource {
  key: string;
  label: string;
  blob: Blob;
  previewUrl: string;
}

interface Props {
  takes: Take[];
  value: AudioSource | null;
  onChange: (s: AudioSource | null) => void;
  disabled?: boolean;
}

const MAX_FILE_BYTES = 100 * 1024 * 1024;

export function SourcePicker({ takes, value, onChange, disabled }: Props) {
  const [tab, setTab] = useState<'take' | 'file'>('take');
  const [error, setError] = useState<string | null>(null);
  const owned = useRef<string | null>(null);

  const release = () => {
    if (owned.current) {
      URL.revokeObjectURL(owned.current);
      owned.current = null;
    }
  };
  useEffect(() => release, []);

  const adopt = (key: string, label: string, blob: Blob) => {
    release();
    const url = URL.createObjectURL(blob);
    owned.current = url;
    onChange({ key, label, blob, previewUrl: url });
  };

  const pickTake = async (id: string) => {
    setError(null);
    if (!id) {
      release();
      onChange(null);
      return;
    }
    const t = takes.find((x) => x.id === id);
    if (!t) return;
    try {
      adopt(`take:${t.id}`, t.name, await (await fetch(t.url)).blob());
    } catch {
      setError('Could not read that recording.');
    }
  };

  const pickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    if (f.size > MAX_FILE_BYTES) {
      setError('That file is larger than 100 MB.');
      return;
    }
    adopt(`file:${f.name}`, f.name, f);
  };

  const selectedTake = value?.key.startsWith('take:') ? value.key.slice(5) : '';

  return (
    <div className="picker">
      <div className="seg" role="group" aria-label="Audio source">
        <button type="button" className={tab === 'take' ? 'on' : ''} aria-pressed={tab === 'take'} onClick={() => setTab('take')} disabled={disabled}>
          Use a recording
        </button>
        <button type="button" className={tab === 'file' ? 'on' : ''} aria-pressed={tab === 'file'} onClick={() => setTab('file')} disabled={disabled}>
          Upload a file
        </button>
      </div>

      {tab === 'take' ? (
        takes.length === 0 ? (
          <p className="muted small">No recordings yet. Record one above, or upload a file.</p>
        ) : (
          <label className="field">
            <span>Recording</span>
            <select value={selectedTake} onChange={(e) => void pickTake(e.target.value)} disabled={disabled}>
              <option value="">Choose a recording</option>
              {takes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.durationSec.toFixed(1)} s)
                </option>
              ))}
            </select>
          </label>
        )
      ) : (
        <label className="field">
          <span>Audio file (WAV, MP3, M4A, WebM, OGG)</span>
          <input type="file" accept="audio/*" onChange={pickFile} disabled={disabled} />
        </label>
      )}

      {error && <p className="status status-problem">{error}</p>}
      {value && (
        <div className="player">
          <p className="player-label">Selected: {value.label}</p>
          <audio controls src={value.previewUrl} preload="metadata" />
        </div>
      )}
    </div>
  );
}
