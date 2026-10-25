// Typed client for the Voice Bridge API. All errors are normalised into ApiError with a user-safe message.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export const apiUrl = (path: string) => `${API_BASE}${path}`;

export const CONSENT_STATEMENT =
  "I am the owner of this voice, or I have the speaker's explicit permission to create and use a voice profile from it.";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

export type ModelState = 'unavailable' | 'loading' | 'ready' | 'error';

export interface ModelStatus {
  state: ModelState;
  engine: string;
  display_name: string;
  license: string;
  reason: string | null;
  device: string | null;
  sample_rate: number | null;
  weights_hint: string | null;
}

export interface Voice {
  id: string;
  name: string;
  mode: 'quick' | 'hq';
  created_at: string;
  engine: string;
  artifact: string;
  reference_seconds: number;
  segments: number;
  warnings: string[];
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface Job {
  id: string;
  status: JobStatus;
  profile_id: string;
  source_seconds: number;
  output_seconds: number | null;
  processing_seconds: number | null;
  rtf: number | null;
  device: string | null;
  engine: string | null;
  error: { code: string; message: string } | null;
  audio_url: string | null;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 120000): Promise<T> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { ...init, signal: ctl.signal });
  } catch (e) {
    if ((e as { name?: string } | null)?.name === 'AbortError') {
      throw new ApiError('timeout', 'The server took too long to respond.');
    }
    throw new ApiError('network', 'Cannot reach the server. Make sure the backend is running.');
  } finally {
    window.clearTimeout(timer);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* response was not JSON */
  }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(err?.code ?? 'http_error', err?.message ?? `The server returned an error (${res.status}).`, res.status);
  }
  return body as T;
}

export const getModelStatus = () => request<ModelStatus>('/api/model/status', {}, 5000);
export const listVoices = () => request<{ voices: Voice[] }>('/api/voices', {}, 10000);
export const enrollVoice = (form: FormData) =>
  request<{ voice: Voice; quality: { verdict: string } }>('/api/voices', { method: 'POST', body: form }, 300000);
export const deleteVoice = (id: string) => request<{ deleted: boolean }>(`/api/voices/${id}`, { method: 'DELETE' }, 10000);
export const startConversion = (form: FormData) =>
  request<{ job: Job; warnings: string[] }>('/api/convert', { method: 'POST', body: form }, 120000);
export const getJob = (id: string) => request<{ job: Job }>(`/api/jobs/${id}`, {}, 10000);
export const deleteJob = (id: string) => request<{ deleted: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }, 10000);
