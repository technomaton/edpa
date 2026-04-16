import type { ReactNode } from 'react';

interface DashboardBandProps {
  band: string;
  label: string;
  sublabel: string;
  color: string;
  children: ReactNode;
}

export function DashboardBand({ band, label, sublabel, color, children }: DashboardBandProps) {
  return (
    <div className={`dashboard-band dashboard-band--${band}`}>
      <div className="dashboard-band__label" style={{ background: color }}>
        <span className="dashboard-band__name">{label}</span>
        <span className="dashboard-band__sub">{sublabel}</span>
      </div>
      <div className="dashboard-band__content">
        {children}
      </div>
    </div>
  );
}
