import React from 'react';

export default function LoadingSpinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100px' }}>
      <div className="spinner" style={{ width: '40px', height: '40px', color: 'var(--accent)' }} />
    </div>
  );
}
