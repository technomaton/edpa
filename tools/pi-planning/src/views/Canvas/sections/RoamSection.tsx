import { useMemo } from 'react';
import type { WorkItem, RoamStatus } from '../../../types/edpa';

interface Props {
  items: unknown[];
  selectedPI: string | null;
  isReadonly: boolean;
  width: number;
  height: number;
}

const QUADRANTS: { status: RoamStatus; label: string; bg: string; headerBg: string }[] = [
  { status: 'resolved',  label: 'Resolved',  bg: 'rgba(5,150,105,0.06)',  headerBg: '#059669' },
  { status: 'owned',     label: 'Owned',     bg: 'rgba(30,41,59,0.06)',   headerBg: '#1e293b' },
  { status: 'accepted',  label: 'Accepted',  bg: 'rgba(234,88,12,0.06)',  headerBg: '#ea580c' },
  { status: 'mitigated', label: 'Mitigated', bg: 'rgba(100,116,139,0.06)',headerBg: '#64748b' },
];

const SEV_COLORS: Record<string, string> = {
  high: '#dc2626', medium: '#d97706', low: '#059669',
};

export function RoamSection({ items: rawItems, selectedPI, width }: Props) {
  const items = rawItems as WorkItem[];

  const risks = useMemo(() =>
    items.filter(i => {
      if (i.type !== 'Risk') return false;
      if (!i.iteration) return true; // risks without iteration always show
      if (!selectedPI) return true;
      // Match: PI-2026-1 matches PI-2026-1, PI-2026-1.x matches PI-2026-1
      return i.iteration.startsWith(selectedPI) || selectedPI.startsWith(i.iteration);
    }),
    [items, selectedPI],
  );

  const unclassified = risks.filter(r => !r.roam_status);

  return (
    <div className="roam-section" style={{ width }}>
      {/* Unclassified risks — to be sorted into quadrants */}
      {unclassified.length > 0 && (
        <div className="roam-section__unclassified">
          <div className="roam-section__uncl-header">
            Unclassified Risks ({unclassified.length})
          </div>
          <div className="roam-section__uncl-body">
            {unclassified.map(r => (
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
      )}
      <div className="roam-section__quadrants">
        {QUADRANTS.map(q => {
          const qRisks = risks.filter(r => r.roam_status === q.status);
          return (
            <div key={q.status} className="roam-section__quad" style={{ background: q.bg }}>
              <div className="roam-section__quad-header" style={{ background: q.headerBg }}>
                {q.label} <span className="roam-section__quad-count">#{qRisks.length}</span>
              </div>
              <div className="roam-section__quad-body">
                {qRisks.map(r => (
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
