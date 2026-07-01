// ── Flask API Client ─────────────────────────────────────────────────────────
// All calls go to the Flask backend at http://localhost:8501

import type {
  AppConfig,
  ProfileResponse,
  StatusResponse,
  ResultsResponse,
  SaveEditsPayload,
} from './types';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8501';

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
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

// ── Auth ─────────────────────────────────────────────────────────────────────

export const api = {
  getConfig: () => apiFetch<AppConfig>('/api/config'),

  getProfile: () => apiFetch<ProfileResponse>('/api/profile'),

  logout: () =>
    apiFetch<{ success: boolean }>('/api/logout', { method: 'POST' }),

  // ── Uploads ────────────────────────────────────────────────────────────────

  uploadApk: async (file: File): Promise<{ success: boolean; filename: string }> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE_URL}/api/upload/apk`, {
      method: 'POST',
      body: fd,
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
