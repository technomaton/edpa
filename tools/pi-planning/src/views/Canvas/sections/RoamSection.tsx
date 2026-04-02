import { useMemo } from 'react';
import type { WorkItem, RoamStatus } from '../../../types/edpa';

interface Props {
  items: unknown[];
  selectedPI: string | null;
  isReadonly: boolean;
  width: number;
  height: number;
}

const ROAM_COLUMNS: { status: RoamStatus; label: string; color: string }[] = [
  { status: 'resolved', label: 'Resolved', color: '#059669' },
  { status: 'owned', label: 'Owned', color: '#6366f1' },
  { status: 'accepted', label: 'Accepted', color: '#d97706' },
  { status: 'mitigated', label: 'Mitigated', color: '#0891b2' },
];

const SEV_COLORS: Record<string, string> = {
  high: '#dc2626', medium: '#d97706', low: '#059669',
};

export function RoamSection({ items: rawItems, selectedPI, width, height }: Props) {
  const items = rawItems as WorkItem[];

  const risks = useMemo(() =>
    items.filter(i => i.type === 'Risk' && i.iteration?.startsWith(selectedPI || '')),
    [items, selectedPI],
  );

  return (
    <div className="roam-section" style={{ width, height, overflow: 'auto' }}>
      <div className="roam-section__grid">
        {ROAM_COLUMNS.map(col => {
          const colRisks = risks.filter(r => r.roam_status === col.status);
          return (
            <div key={col.status} className="roam-section__column">
              <div className="roam-section__col-header" style={{ background: col.color }}>
                {col.label} ({colRisks.length})
              </div>
              <div className="roam-section__col-body">
                {colRisks.map(r => (
                  <div key={r.id} className="roam-section__card">
                    <div className="roam-section__card-head">
                      <span className="roam-section__card-id">{r.id}</span>
                      <span className="roam-section__card-sev" style={{
                        color: SEV_COLORS[r.severity || 'medium'],
                      }}>{r.severity || 'medium'}</span>
                    </div>
                    <span className="roam-section__card-title">{r.title}</span>
                    <span className="roam-section__card-owner">{r.owner || r.assignee || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
