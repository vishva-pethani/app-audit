'use client';

import { useRef, useState, useCallback } from 'react';
import { api, extractDriveFileId } from '@/lib/api';

type FileType = 'apk' | 'schema';
type SourceMode = 'local' | 'drive' | 'sheets';

interface FileUploadProps {
  type: FileType;
  isGoogleConnected: boolean;
  googleClientId: string;
  googleRedirectUri: string;
  onUploaded: (filename: string) => void;
}

export default function FileUpload({
  type,
  isGoogleConnected,
  googleClientId,
  googleRedirectUri,
  onUploaded,
}: FileUploadProps) {
  const [mode, setMode] = useState<SourceMode>('local');
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isApk = type === 'apk';
  const accept = isApk ? '.apk' : '.xlsx,.xls,.csv';
  const label = isApk ? 'Target Android APK' : 'Event Schema Sheet';
  const icon = isApk ? '📦' : '📊';
  const driveMode = isApk ? 'drive' : 'sheets';
  const driveModeLabel = isApk ? 'Google Drive' : 'Google Sheets URL';
  const urlPlaceholder = isApk
    ? 'Paste Google Drive link or File ID'
    : 'Paste Google Spreadsheet URL';

  const uploadFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const result = isApk ? await api.uploadApk(file) : await api.uploadSchema(file);
        setUploaded(result.filename);
        onUploaded(result.filename);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [isApk, onUploaded]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadFile(file);
  };

  const handleResolveUrl = async () => {
    if (!urlInput.trim()) return;
    setResolving(true);
    setError(null);
    try {
      let result: { success: boolean; filename: string };
      if (isApk) {
        const fileId = extractDriveFileId(urlInput.trim());
        result = await api.resolveDriveApk(fileId, 'drive_file.apk');
      } else {
        result = await api.resolveSheetSchema(urlInput.trim());
      }
      setUploaded(result.filename);
      onUploaded(result.filename);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Resolution failed');
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="glass-card p-3" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Card title */}
      <div className="section-title">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
          {isApk ? (
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          ) : (
            <>
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="3" y1="9" x2="21" y2="9" />
              <line x1="9" y1="21" x2="9" y2="9" />
            </>
          )}
        </svg>
        {icon} {label}
      </div>

      {/* Source toggle */}
      <div className="segmented">
        <button
          className={`segmented-btn${mode === 'local' ? ' active' : ''}`}
          onClick={() => { setMode('local'); setError(null); }}
        >
          💻 Local Upload
        </button>
        <button
          className={`segmented-btn${mode === driveMode ? ' active' : ''}`}
          onClick={() => { setMode(driveMode as SourceMode); setError(null); }}
        >
          ☁️ {driveModeLabel}
        </button>
      </div>

      {/* Local Upload Zone */}
      {mode === 'local' && (
        <div
          className={`upload-zone${dragOver ? ' drag-over' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={accept}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <div style={{ pointerEvents: 'none' }}>
            {uploading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--accent)' }}>
                <span className="spinner" style={{ borderTopColor: 'var(--accent)' }} />
                Uploading…
              </div>
            ) : uploaded ? (
              <div className="text-success" style={{ fontWeight: 600 }}>
                ✓ {uploaded}
              </div>
            ) : (
              <>
                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
                  {isApk ? '📦' : '📄'}
                </div>
                <div style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                  <strong style={{ color: 'var(--text-primary)' }}>Click to select</strong> or drag & drop
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                  {accept} supported
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Drive / Sheets URL input */}
      {mode !== 'local' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {!isGoogleConnected ? (
            <div
              style={{
                padding: '1rem',
                background: 'rgba(239,68,68,0.05)',
                border: '1px dashed rgba(239,68,68,0.4)',
                borderRadius: 'var(--radius-md)',
                textAlign: 'center',
              }}
            >
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                ⚠️ Connect your Google account to use {driveModeLabel}
              </p>
              <button
                className="btn-google"
                style={{ fontSize: '0.85rem', padding: '8px 16px' }}
                onClick={() => {
                  const { buildOAuthUrl } = require('@/lib/api');
                  window.location.replace(buildOAuthUrl(googleClientId, googleRedirectUri));
                }}
              >
                <svg viewBox="0 0 24 24" width="16" height="16">
                  <path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.275 1.565-1.88 4.604-6.887 4.604-4.33 0-7.859-3.578-7.859-8s3.53-8 7.859-8c2.46 0 4.105 1.025 5.047 1.926l3.256-3.133C18.28 1.705 15.49 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c6.478 0 10.793-4.537 10.793-10.984 0-.742-.08-1.302-.178-1.782h-10.62z" />
                </svg>
                Connect Google Account
              </button>
            </div>
          ) : (
            <>
              <input
                className="input"
                type="text"
                placeholder={urlPlaceholder}
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleResolveUrl()}
              />
              <span className="text-xs text-secondary">
                {isApk
                  ? 'Supports full Drive links or bare File IDs'
                  : 'Paste full Google Sheets URL — sheet will be fetched using your credentials'}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={handleResolveUrl}
                disabled={resolving || !urlInput.trim()}
                style={{ alignSelf: 'flex-start' }}
              >
                {resolving ? (
                  <>
                    <span className="spinner" style={{ width: 14, height: 14, borderTopColor: 'var(--text-primary)' }} />
                    Resolving…
                  </>
                ) : uploaded ? (
                  `✓ ${uploaded}`
                ) : (
                  `Resolve & Fetch ${isApk ? 'APK' : 'Sheet'}`
                )}
              </button>
            </>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-error" style={{ marginTop: -4 }}>
          ❌ {error}
        </p>
      )}
    </div>
  );
}
