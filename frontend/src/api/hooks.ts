import { useCallback, useEffect, useState } from 'react';
import { getModelStatus, listVoices, type ModelStatus, type Voice } from './client';

export function useModelStatus() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      let next = 15000;
      try {
        const s = await getModelStatus();
        if (cancelled) return;
        setStatus(s);
        setOffline(false);
        if (s.state === 'loading') next = 2000;
        else if (s.state !== 'ready') next = 5000;
      } catch {
        if (cancelled) return;
        setOffline(true);
        next = 5000;
      }
      timer = window.setTimeout(tick, next);
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return { status, offline };
}

export function useVoices(serverUp: boolean) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setVoices((await listVoices()).voices);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load voices.');
    }
  }, []);

  useEffect(() => {
    if (serverUp) void refresh();
  }, [serverUp, refresh]);

  return { voices, error, refresh };
}
