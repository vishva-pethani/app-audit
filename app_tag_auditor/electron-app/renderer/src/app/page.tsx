'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { AppConfig, ProfileResponse, StatusResponse, ResultsResponse } from '@/lib/types';
import Header from '@/components/Header';
import FileUpload from '@/components/FileUpload';
import LogViewer from '@/components/LogViewer';
import HitlModal from '@/components/HitlModal';
import ResultsTable from '@/components/ResultsTable';
import StatusBadge from '@/components/StatusBadge';
import LoadingSpinner from '@/components/LoadingSpinner';

export default function Home() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const [apkFilename, setApkFilename] = useState<string | null>(null);
  const [schemaFilename, setSchemaFilename] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // Fetch initial profile & config
  const initData = async () => {
    try {
      const cfg = await api.getConfig();
      setConfig(cfg);
      const prof = await api.getProfile();
      setProfile(prof);
    } catch (err) {
      console.error('Init data fetch failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    initData();
  }, []);

  // Poll status when running
  useEffect(() => {
    let interval: NodeJS.Timeout;
    const fetchStatus = async () => {
      try {
        const stat = await api.getStatus();
        setStatus(stat);
        
        if (stat.status === 'running') {
          setRunning(true);
        } else {
          setRunning(false);
          // if completed, fetch results once
          if (stat.status === 'completed' && !results) {
            fetchResults();
          }
        }
      } catch (err) {
        console.error('Status poll failed:', err);
      }
    };

    fetchStatus(); // initial check
    interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [results]);

  const fetchResults = async () => {
    try {
      const res = await api.getResults();
      setResults(res);
    } catch (err) {
      console.error('Results fetch failed:', err);
    }
  };

  const handleRunPipeline = async () => {
    if (!apkFilename || !schemaFilename) return;
    setRunError(null);
    setRunning(true);
    setResults(null); // clear old results
    try {
      await api.runPipeline();
    } catch (e: any) {
      setRunError(e.message || 'Failed to start pipeline');
      setRunning(false);
    }
  };

  const handleHitlSubmit = async (decision: string, credentials?: Record<string, string>) => {
    try {
      await api.respondHitl(decision, credentials);
    } catch (err) {
      console.error('HITL response submission failed:', err);
    }
  };

  // Google OAuth redirect interception: check url search params for ?code
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('code');
    if (code) {
      // clear search params and notify parent / reload profile
      window.history.replaceState({}, document.title, window.location.pathname);
      initData();
    }
  }, []);

  if (loading) return <LoadingSpinner />;

  const isGoogleConnected = !!profile?.authenticated;
  const canRun = !!apkFilename && !!schemaFilename && !running;

  return (
    <div className="page-wrapper">
      <div className="bg-ambient">
        <div className="bg-blob bg-blob-1" />
        <div className="bg-blob bg-blob-2" />
        <div className="bg-blob bg-blob-3" />
      </div>

      <Header profile={profile?.profile || null} onProfileChange={initData} />

      <main className="container p-4" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '2rem' }}>
        <div className="grid-2">
          {/* APK Selection */}
          <FileUpload
            type="apk"
            isGoogleConnected={isGoogleConnected}
            googleClientId={config?.google_client_id || ''}
            googleRedirectUri={config?.google_redirect_uri || ''}
            onUploaded={setApkFilename}
          />

          {/* Schema Selection */}
          <FileUpload
            type="schema"
            isGoogleConnected={isGoogleConnected}
            googleClientId={config?.google_client_id || ''}
            googleRedirectUri={config?.google_redirect_uri || ''}
            onUploaded={setSchemaFilename}
          />
        </div>

        {/* Start button */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div className="flex items-center justify-between">
            <button
              className="btn btn-primary"
              style={{ padding: '1rem 2rem', fontSize: '1.05rem', minWidth: 260 }}
              disabled={!canRun}
              onClick={handleRunPipeline}
            >
              🚀 Run Analytics Audit Pipeline
            </button>

            {status && (
              <div className="flex items-center gap-1">
                <span className="text-secondary text-sm">Status:</span>
                <StatusBadge status={status.status} />
              </div>
            )}
          </div>
          {runError && <p className="text-xs text-error">{runError}</p>}
        </div>

        {/* Terminal Live logs */}
        <LogViewer logs={status?.logs || ''} status={status?.status || 'idle'} />

        {/* Results spreadsheet */}
        {results && (
          <ResultsTable results={results} onRefresh={fetchResults} />
        )}
      </main>

      {/* HITL overlay */}
      {status?.hitl && (
        <HitlModal hitl={status.hitl} onSubmit={handleHitlSubmit} />
      )}
    </div>
  );
}
