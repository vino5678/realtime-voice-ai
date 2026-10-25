import type { ModelStatus } from '../api/client';

export function ModelBadge({ status }: { status: ModelStatus | null }) {
  if (!status) return null;
  if (status.state === 'ready') {
    return (
      <span className="api api-on" title={`${status.display_name}, ${status.device ?? 'unknown device'}`}>
        Voice model ready ({status.device?.startsWith('cuda') ? 'GPU' : 'CPU'})
      </span>
    );
  }
  if (status.state === 'loading') return <span className="api api-wait">Voice model loading…</span>;
  return (
    <span className="api api-off" title={status.reason ?? ''}>
      Voice model unavailable
    </span>
  );
}

export function ModelNotice({ status }: { status: ModelStatus | null }) {
  if (!status || status.state === 'ready') return null;
  return (
    <aside className="consent" role="status">
      <strong>{status.state === 'loading' ? 'Voice model is loading.' : 'Voice model is not available.'}</strong>{' '}
      {status.reason} Enrollment and conversion stay disabled until it is ready.
    </aside>
  );
}

export function modelWaitMessage(status: ModelStatus | null): string {
  if (!status) return 'Cannot read the voice model status. Is the backend running on port 8000?';
  if (status.state === 'loading') return 'The voice model is still loading.';
  const what = status.state === 'error' ? 'failed to load' : 'is unavailable';
  return `Voice model ${what}: ${status.reason ?? 'no reason reported'}`;
}
