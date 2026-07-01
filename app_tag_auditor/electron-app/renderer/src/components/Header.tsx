'use client';

import { UserProfile } from '@/lib/types';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

interface HeaderProps {
  profile: UserProfile | null;
  onProfileChange?: () => void;
}

export default function Header({ profile, onProfileChange }: HeaderProps) {
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await api.logout();
      onProfileChange?.();
      router.push('/');
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '1.25rem 1.5rem',
        borderBottom: '1px solid var(--card-border)',
        backdropFilter: 'blur(20px)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
        background: 'rgba(8,12,21,0.85)',
      }}
    >
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.9rem' }}>
        <div
          style={{
            width: 44,
            height: 44,
            background: 'var(--gradient)',
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 18px rgba(255,143,0,0.35)',
            flexShrink: 0,
          }}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="white" strokeWidth="2.5">
            <rect x="3" y="11" width="18" height="10" rx="2" />
            <circle cx="12" cy="5" r="2" />
            <path d="M12 7v4" />
          </svg>
        </div>
        <div>
          <h1
            className="gradient-text"
            style={{ fontSize: '1.45rem', fontWeight: 800, letterSpacing: '-0.5px', lineHeight: 1 }}
          >
            App Tag Auditor
          </h1>
          <p style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', marginTop: 3 }}>
            Automated Firebase Analytics APK Auditing
          </p>
        </div>
      </div>

      {/* Nav + Profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {profile ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              background: 'var(--card-bg)',
              border: '1px solid var(--card-border)',
              borderRadius: 100,
              padding: '0.45rem 1rem 0.45rem 0.5rem',
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={profile.picture}
              alt={profile.name}
              width={30}
              height={30}
              style={{ borderRadius: '50%', border: '1.5px solid var(--accent)' }}
            />
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, lineHeight: 1 }}>
                {profile.name}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1, marginTop: 2 }}>
                {profile.email}
              </div>
            </div>
            <button
              className="btn btn-sm btn-secondary"
              onClick={handleLogout}
              disabled={loggingOut}
              style={{ marginLeft: 4, fontSize: '0.78rem' }}
            >
              {loggingOut ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        ) : (
          <div
            style={{
              fontSize: '0.82rem',
              color: 'var(--text-muted)',
              background: 'var(--card-bg)',
              border: '1px solid var(--card-border)',
              borderRadius: 100,
              padding: '0.45rem 1rem',
            }}
          >
            Not signed in
          </div>
        )}
      </div>
    </header>
  );
}
