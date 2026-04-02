import { useMemo, useState } from 'react';
import type { WorkItem, PIConfig } from '../../../types/edpa';

interface Props {
  items: unknown[];
  pi: unknown;
  width: number;
  height: number;
}

type SortKey = 'wsjf' | 'bv' | 'tc' | 'rr' | 'js';

export function PrioritizationSection({ items: rawItems, pi: rawPi, width, height }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;
  const [sortBy, setSortBy] = useState<SortKey>('wsjf');
  const [sortAsc, setSortAsc] = useState(false);

  const features = useMemo(() => {
    const iterationIds = new Set(pi?.iterations.map(it => it.id) || []);
    const filtered = items.filter(i => {
      if (i.type !== 'Feature') return false;
      if (!i.iteration) return true;
      return iterationIds.has(i.iteration) || (pi?.iterations || []).some(it => i.iteration!.startsWith(it.id));
    });
    return [...filtered].sort((a, b) => {
      const aVal = (a[sortBy] as number) ?? 0;
      const bVal = (b[sortBy] as number) ?? 0;
      return sortAsc ? aVal - bVal : bVal - aVal;
    });
  }, [items, pi, sortBy, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) setSortAsc(!sortAsc);
    else { setSortBy(key); setSortAsc(false); }
  };

  return (
    <div className="prio-section" style={{ width }}>
      <table className="prio-section__table">
        <thead>
          <tr>
            <th>#</th>
            <th>ID</th>
            <th>Title</th>
            <th onClick={() => toggleSort('bv')} style={{ cursor: 'pointer' }}>BV{sortBy === 'bv' ? (sortAsc ? ' ▲' : ' ▼') : ''}</th>
            <th onClick={() => toggleSort('tc')} style={{ cursor: 'pointer' }}>TC</th>
            <th onClick={() => toggleSort('rr')} style={{ cursor: 'pointer' }}>RR</th>
            <th onClick={() => toggleSort('js')} style={{ cursor: 'pointer' }}>JS</th>
            <th onClick={() => toggleSort('wsjf')} style={{ cursor: 'pointer' }}>WSJF{sortBy === 'wsjf' ? (sortAsc ? ' ▲' : ' ▼') : ''}</th>
            <th>Status</th>
            <th>Owner</th>
          </tr>
        </thead>
        <tbody>
          {features.map((item, idx) => (
            <tr key={item.id} style={{ opacity: item.status === 'Done' ? 0.45 : 1 }}>
              <td style={{ textAlign: 'center', color: '#8892a8' }}>{idx + 1}</td>
              <td style={{ color: '#0891b2', fontWeight: 700 }}>{item.id}</td>
              <td>{item.title}</td>
              <td style={{ color: '#059669' }}>{item.bv ?? '-'}</td>
              <td style={{ color: '#ea580c' }}>{item.tc ?? '-'}</td>
              <td style={{ color: '#0891b2' }}>{item.rr ?? '-'}</td>
              <td style={{ color: '#d97706' }}>{item.js ?? '-'}</td>
              <td style={{ color: '#6366f1', fontWeight: 700 }}>{item.wsjf?.toFixed(2) ?? '-'}</td>
              <td>{item.status}</td>
              <td>{item.owner || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
