'use client';

import { PipelineStatus } from '@/lib/types';

interface StatusBadgeProps {
  status: PipelineStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const getBadgeClass = () => {
    switch (status) {
      case 'running':
        return 'status-running';
      case 'completed':
        return 'status-completed';
      case 'error':
        return 'status-error';
      default:
        return 'status-idle';
    }
  };

  return (
    <div className={`status-badge ${getBadgeClass()}`}>
      {status === 'running' && <span className="pulse" />}
      <span style={{ textTransform: 'uppercase' }}>{status}</span>
    </div>
  );
}
