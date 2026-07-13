// ── Flask API Client ─────────────────────────────────────────────────────────
// All calls go to the Flask backend at http://localhost:8501

import type {
  AppConfig,
  ProfileResponse,
  StatusResponse,
  ResultsResponse,
  SaveEditsPayload,
} from './types';

const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined' && (window as any).electronAPI?.getApiBaseUrl) {
    return (window as any).electronAPI.getApiBaseUrl();
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8501';
};

const BASE_URL = getApiBaseUrl();

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/**
 * Retry wrapper for startup API calls.
 * Flask needs a few seconds to start inside the Electron process, especially on Windows.
 * This retries with exponential backoff for up to `maxMs` milliseconds.
 */
async function withStartupRetry<T>(
  fn: () => Promise<T>,
  maxMs = 30_000,
  baseDelayMs = 500
): Promise<T> {
  const deadline = Date.now() + maxMs;
  let delay = baseDelayMs;
  let lastErr: unknown;
  while (Date.now() < deadline) {
    try {
      return await fn();
    } catch (err: any) {
      lastErr = err;
      // Only retry on network/fetch errors, not on 4xx/5xx HTTP errors
      const isNetworkErr =
        err?.message === 'Failed to fetch' ||
        err?.message?.includes('fetch') ||
        err?.message?.includes('network') ||
        err?.message?.includes('ECONNREFUSED');
      if (!isNetworkErr) throw err;
      await new Promise((r) => setTimeout(r, Math.min(delay, 4000)));
      delay = Math.min(delay * 1.5, 4000);
    }
  }
  throw lastErr;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export const api = {
  // Startup calls use withStartupRetry — Flask may still be booting (esp. on Windows)
  getConfig: () => withStartupRetry(() => apiFetch<AppConfig>('/api/config')),

  getProfile: () => withStartupRetry(() => apiFetch<ProfileResponse>('/api/profile')),

  logout: () =>
    apiFetch<{ success: boolean }>('/api/logout', { method: 'POST' }),

  // ── Uploads ────────────────────────────────────────────────────────────────

  uploadApk: async (file: File): Promise<{ success: boolean; filename: string }> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE_URL}/api/upload/apk`, {
      method: 'POST',
      body: fd,
      credentials: 'include',
    });
    if (!res.ok) throw new Error('APK upload failed');
    return res.json();
  },

  uploadSchema: async (file: File): Promise<{ success: boolean; filename: string }> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE_URL}/api/upload/schema`, {
      method: 'POST',
      body: fd,
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Schema upload failed');
    return res.json();
  },

  // ── Google Drive / Sheets ──────────────────────────────────────────────────

  resolveDriveApk: (fileId: string, fileName: string) =>
    apiFetch<{ success: boolean; filename: string }>('/api/drive/picker', {
      method: 'POST',
      body: JSON.stringify({ file_id: fileId, file_name: fileName }),
    }),

  resolveSheetSchema: (sheetUrl: string) =>
    apiFetch<{ success: boolean; filename: string }>('/api/sheets/picker', {
      method: 'POST',
      body: JSON.stringify({ sheet_url: sheetUrl }),
    }),

  // ── Pipeline ───────────────────────────────────────────────────────────────

  runPipeline: () =>
    apiFetch<{ success: boolean }>('/api/run', { method: 'POST' }),

  getStatus: () => apiFetch<StatusResponse>('/api/status'),

  respondHitl: (decision: string, credentials: Record<string, string> = {}) =>
    apiFetch<{ success: boolean }>('/api/hitl/respond', {
      method: 'POST',
      body: JSON.stringify({ decision, credentials }),
    }),

  // ── Results ────────────────────────────────────────────────────────────────

  getResults: () => apiFetch<ResultsResponse>('/api/results'),

  saveEdits: (payload: SaveEditsPayload) =>
    apiFetch<{ success: boolean }>('/api/results/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  downloadResultsUrl: () => `${BASE_URL}/api/results/download`,
};

// ── Utility: extract Google Drive file ID from URL ────────────────────────────

export function extractDriveFileId(urlOrId: string): string {
  if (urlOrId.includes('/file/d/')) {
    return urlOrId.split('/file/d/')[1].split('/')[0];
  }
  if (urlOrId.includes('id=')) {
    return urlOrId.split('id=')[1].split('&')[0];
  }
  return urlOrId; // assume it's already a bare ID
}

// ── Utility: build Google OAuth URL ─────────────────────────────────────────

export function buildOAuthUrl(clientId: string, redirectUri: string): string {
  const scopes = [
    'openid',
    'email',
    'profile',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
  ].join(' ');

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: scopes,
    access_type: 'offline',
    prompt: 'consent',
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}
