'use client';

import { useState } from 'react';
import { HitlInfo } from '@/lib/types';

interface HitlModalProps {
  hitl: HitlInfo;
  onSubmit: (decision: string, credentials?: Record<string, string>) => void;
}

export default function HitlModal({ hitl, onSubmit }: HitlModalProps) {
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFieldChange = (name: string, value: string) => {
    setCredentials(prev => ({ ...prev, [name]: value }));
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    onSubmit('submit_fields', credentials);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box flex flex-col gap-3">
        <div className="hitl-title" style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <rect x="3" y="11" width="18" height="10" rx="2" />
            <circle cx="12" cy="5" r="2" />
            <path d="M12 7v4" />
          </svg>
          🔑 Authentication Prompt
        </div>

        <p className="text-secondary text-sm">
          {hitl.mid_login_fields 
            ? 'The app requires mid-login fields or multi-factor code to proceed.' 
            : 'The device has encountered a login or verification screen. Please provide credentials to proceed.'}
        </p>

        {hitl.fields && hitl.fields.length > 0 ? (
          <form onSubmit={handleFormSubmit} className="flex flex-col gap-2">
            {hitl.fields.map(field => (
              <div key={field.name} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <label className="label" style={{ fontSize: '0.75rem' }}>{field.name}</label>
                <input
                  className="input"
                  type={field.type === 'password' ? 'password' : 'text'}
                  placeholder={field.placeholder || `Enter ${field.name}`}
                  value={credentials[field.name] || ''}
                  onChange={(e) => handleFieldChange(field.name, e.target.value)}
                  required
                />
              </div>
            ))}

            <button
              type="submit"
              className="btn btn-primary mt-2"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Credentials'}
            </button>
          </form>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <button
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={() => onSubmit('login')}
              >
                🔐 Start Login
              </button>
              <button
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={() => onSubmit('signup')}
              >
                📝 Start Signup
              </button>
            </div>
          </div>
        )}

        {hitl.escape_options && hitl.escape_options.length > 0 && (
          <div className="flex flex-col gap-1 mt-2">
            <div className="label" style={{ fontSize: '0.75rem', color: 'var(--accent)' }}>Or select escape path:</div>
            <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
              {hitl.escape_options.map(opt => (
                <button
                  key={opt}
                  className="btn btn-secondary btn-sm"
                  onClick={() => onSubmit(opt)}
                >
                  🎯 {opt}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2 mt-2" style={{ borderTop: '1px solid var(--card-border)', paddingTop: '1rem' }}>
          <button
            className="btn btn-secondary"
            style={{ flex: 1 }}
            onClick={() => onSubmit('skip')}
          >
            ⬅️ Skip / Go Back
          </button>
          <button
            className="btn btn-danger"
            style={{ flex: 1 }}
            onClick={() => onSubmit('abort')}
          >
            🛑 Abort Audit
          </button>
        </div>
      </div>
    </div>
  );
}
