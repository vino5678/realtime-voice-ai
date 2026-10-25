import { useEffect, useState } from 'react';

type Health =
  | { state: 'checking' }
  | { state: 'online'; version: string; python: string; inference: boolean }
  | { state: 'offline' };

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export function ApiStatus() {
  const [health, setHealth] = useState<Health>({ state: 'checking' });

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const ctl = new AbortController();
      const timeout = window.setTimeout(() => ctl.abort(), 3000);
      try {
        const res = await fetch(`${API_BASE}/api/health`, { signal: ctl.signal });
        if (!res.ok) throw new Error(String(res.status));
        const body = await res.json();
        if (!cancelled)
          setHealth({
            state: 'online',
            version: String(body.version),
            python: String(body.python),
            inference: Boolean(body.inference?.available),
          });
      } catch {
        if (!cancelled) setHealth({ state: 'offline' });
      } finally {
        window.clearTimeout(timeout);
      }
    };
    void check();
    const id = window.setInterval(check, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (health.state === 'checking') return <span className="api api-wait">Checking server…</span>;
  if (health.state === 'offline')
    return (
      <span className="api api-off" title="Start the backend: see README step 5">
        Server offline
      </span>
    );
  return (
    <span className="api api-on" title={`API v${health.version}, Python ${health.python}`}>
      Server online{health.inference ? '' : ', no AI model loaded'}
    </span>
  );
}
