'use client';

import { useState } from 'react';

interface LogViewerProps {
  logs: string;
  status: string;
}

export default function LogViewer({ logs, status }: LogViewerProps) {
  const [filter, setFilter] = useState<'all' | 'info' | 'warning' | 'error'>('all');

  const lines = logs.split('\n').filter(line => line.trim() !== '');

  const getLineClass = (line: string) => {
    const lower = line.toLowerCase();
    if (lower.includes('error') || lower.includes('exception') || lower.includes('failed')) {
      return 'log-line-error';
    }
    if (lower.includes('warning') || lower.includes('warn')) {
      return 'log-line-warning';
    }
    if (lower.includes('success') || lower.includes('completed') || lower.includes('✓')) {
      return 'log-line-success';
    }
    return 'log-line-info';
  };

  const filteredLines = lines.filter(line => {
    if (filter === 'all') return true;
    const lower = line.toLowerCase();
    if (filter === 'error') return lower.includes('error') || lower.includes('exception') || lower.includes('failed');
    if (filter === 'warning') return lower.includes('warning') || lower.includes('warn');
    if (filter === 'info') return !lower.includes('error') && !lower.includes('exception') && !lower.includes('failed') && !lower.includes('warning') && !lower.includes('warn');
    return true;
  });

  return (
    <div className="glass-card p-3 flex flex-col gap-2" style={{ gridColumn: '1 / -1' }}>
      <div className="flex justify-between items-center">
        <div className="section-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
          Live Audit Console Logs
        </div>
        
        <div className="flex items-center gap-1">
          <div className="segmented" style={{ padding: 2 }}>
            {(['all', 'info', 'warning', 'error'] as const).map(f => (
              <button
                key={f}
                className={`segmented-btn btn-sm${filter === f ? ' active' : ''}`}
                onClick={() => setFilter(f)}
                style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem', textTransform: 'capitalize' }}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="terminal">
        {filteredLines.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            {status === 'idle' 
              ? 'Console idle. Select APK and event schema, then run audit...' 
              : 'No logs matching current filter...'}
          </div>
        ) : (
          filteredLines.map((line, idx) => (
            <div key={idx} className={getLineClass(line)}>
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
