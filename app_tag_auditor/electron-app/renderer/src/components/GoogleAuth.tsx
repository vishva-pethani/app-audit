'use client';

import { buildOAuthUrl } from '@/lib/api';

interface GoogleAuthProps {
  clientId: string;
  redirectUri: string;
  label?: string;
  fullWidth?: boolean;
}

export default function GoogleAuth({ clientId, redirectUri, label = 'Connect Google Account', fullWidth }: GoogleAuthProps) {
  const handleLogin = () => {
    if (!clientId) {
      alert('Google Client ID is not configured. Check your .env file.');
      return;
    }
    const url = buildOAuthUrl(clientId, redirectUri);
    window.location.replace(url);
  };

  return (
    <button
      className="btn-google"
      onClick={handleLogin}
      style={fullWidth ? { width: '100%' } : undefined}
    >
      <svg viewBox="0 0 24 24" width="18" height="18">
        <path
          fill="#EA4335"
          d="M12.24 10.285V14.4h6.887c-.275 1.565-1.88 4.604-6.887 4.604-4.33 0-7.859-3.578-7.859-8s3.53-8 7.859-8c2.46 0 4.105 1.025 5.047 1.926l3.256-3.133C18.28 1.705 15.49 1 12.24 1 6.033 1 1 6.033 1 12.24s5.033 11.24 11.24 11.24c6.478 0 10.793-4.537 10.793-10.984 0-.742-.08-1.302-.178-1.782h-10.62z"
        />
      </svg>
      {label}
    </button>
  );
}
