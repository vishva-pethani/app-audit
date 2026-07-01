'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { ResultsResponse, RowChange } from '@/lib/types';

interface ResultsTableProps {
  results: ResultsResponse;
  onRefresh: () => void;
}

export default function ResultsTable({ results, onRefresh }: ResultsTableProps) {
  const [activeSheet, setActiveSheet] = useState<string>('');
  const [editedRows, setEditedRows] = useState<Record<string, Record<string, RowChange>>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (results.sheets && results.sheets.length > 0 && !activeSheet) {
      setActiveSheet(results.sheets[0]);
    }
  }, [results, activeSheet]);

  const sheetData = activeSheet ? results.data[activeSheet] : null;

  const handleCellChange = (rowIdx: number, field: 'status' | 'comments' | 'logs', val: string) => {
    setEditedRows(prev => {
      const sheetChanges = prev[activeSheet] || {};
      const rowChanges = sheetChanges[rowIdx] || {};
      return {
        ...prev,
        [activeSheet]: {
          ...sheetChanges,
          [rowIdx]: {
            ...rowChanges,
            [field]: val as any,
          },
        },
      };
    });
  };

  const handleSave = async () => {
    if (!activeSheet || !editedRows[activeSheet] || Object.keys(editedRows[activeSheet]).length === 0) return;
    setSaving(true);
    setError(null);
    try {
      await api.saveEdits({
        sheet: activeSheet,
        rows: editedRows[activeSheet],
      });
      // clear local updates for this sheet
      setEditedRows(prev => {
        const next = { ...prev };
        delete next[activeSheet];
        return next;
      });
      onRefresh();
    } catch (e: any) {
      setError(e.message || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const getBadgeClass = (status: string) => {
    switch (status) {
      case 'Implemented':
        return 'chip-implemented';
      case 'Implemented with issues':
        return 'chip-issues';
      case 'Scenario Not Found':
        return 'chip-not-found';
      default:
        return 'chip-not-implemented';
    }
  };

  if (!results.sheets || results.sheets.length === 0) {
    return (
      <div className="glass-card p-4 text-center text-secondary">
        No spreadsheet results generated yet. Execute a dry-run or full audit.
      </div>
    );
  }

  const sheetChanges = editedRows[activeSheet] || {};
  const hasChanges = Object.keys(sheetChanges).length > 0;

  return (
    <div className="results-container w-full flex flex-col gap-2" style={{ gridColumn: '1 / -1' }}>
      <div className="results-header flex justify-between items-center">
        <div className="section-title">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          Audit Results Report & Interactive Verification
        </div>
        <a
          href={api.downloadResultsUrl()}
          className="btn btn-secondary btn-sm"
          style={{ textDecoration: 'none' }}
        >
          📥 Download Generated Excel Report
        </a>
      </div>

      {/* Tabs */}
      <div className="tab-strip">
        {results.sheets.map(name => (
          <button
            key={name}
            className={`tab-btn${activeSheet === name ? ' active' : ''}`}
            onClick={() => setActiveSheet(name)}
          >
            {name}
          </button>
        ))}
      </div>

      {/* Table responsive */}
      {sheetData && (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                {sheetData.headers.map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheetData.rows.map((row, idx) => {
                const isSummaryTab = activeSheet === 'Audit Summary';
                const rowChanges = sheetChanges[idx] || {};

                return (
                  <tr key={idx}>
                    {sheetData.headers.map(header => {
                      const value = row[header];

                      // Handle editable fields in non-summary tabs
                      if (!isSummaryTab && header === 'Status') {
                        const currentVal = rowChanges.status || (value as string) || 'Not Implemented';
                        return (
                          <td key={header}>
                            <select
                              className="input select"
                              style={{ padding: '0.3rem 1.5rem 0.3rem 0.6rem', fontSize: '0.8rem', minWidth: 160 }}
                              value={currentVal}
                              onChange={(e) => handleCellChange(idx, 'status', e.target.value)}
                            >
                              <option value="Implemented">Implemented</option>
                              <option value="Implemented with issues">Implemented with issues</option>
                              <option value="Not Implemented">Not Implemented</option>
                              <option value="Scenario Not Found">Scenario Not Found</option>
                            </select>
                          </td>
                        );
                      }

                      if (!isSummaryTab && header === 'Comments') {
                        const currentVal = rowChanges.comments || (value as string) || '';
                        return (
                          <td key={header}>
                            <textarea
                              className="input textarea"
                              style={{ minWidth: 200, fontSize: '0.8rem' }}
                              value={currentVal}
                              onChange={(e) => handleCellChange(idx, 'comments', e.target.value)}
                            />
                          </td>
                        );
                      }

                      if (!isSummaryTab && header === 'Logs') {
                        const currentVal = rowChanges.logs || (value as string) || '';
                        return (
                          <td key={header}>
                            <textarea
                              className="input textarea"
                              style={{ minWidth: 250, fontSize: '0.78rem' }}
                              value={currentVal}
                              onChange={(e) => handleCellChange(idx, 'logs', e.target.value)}
                            />
                          </td>
                        );
                      }

                      // Static badges/cells
                      if (header === 'Status' && isSummaryTab) {
                        return (
                          <td key={header}>
                            <span className={`chip ${getBadgeClass(value as string)}`}>
                              {value}
                            </span>
                          </td>
                        );
                      }

                      return (
                        <td key={header} style={{ whiteSpace: isSummaryTab ? 'nowrap' : 'pre-wrap' }}>
                          {String(value)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {error && <div className="text-xs text-error">{error}</div>}

      {hasChanges && (
        <div style={{ alignSelf: 'flex-end', marginTop: '0.5rem' }}>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving changes...' : '💾 Save Edits to Excel'}
          </button>
        </div>
      )}
    </div>
  );
}
