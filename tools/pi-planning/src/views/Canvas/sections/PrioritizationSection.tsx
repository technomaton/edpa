import { useMemo, useState } from 'react';
import type { WorkItem, PIConfig } from '../../../types/edpa';

interface Props {
  items: unknown[];
  pi: unknown;
  width: number;
  height: number;
}

type SortKey = 'wsjf' | 'bv' | 'tc' | 'rr' | 'js';
type ViewMode = 'table' | 'bubble';

const DONE_STATUSES = new Set(['done', 'closed', 'accepted', 'complete', 'completed']);

function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (DONE_STATUSES.has(s)) return '#059669';
  if (s.includes('implement')) return '#2563eb';
  if (s.includes('validat')) return '#d97706';
  return '#8892a8';
}

// ─── Bubble Chart ─────────────────────────────────────────────────────────────

function WsjfBubbleChart({ items, width }: { items: WorkItem[]; width: number }) {
  const [tooltip, setTooltip] = useState<string | null>(null);

  const chartItems = useMemo(
    () => items.filter(i => (i.bv ?? 0) > 0 || (i.tc ?? 0) > 0),
    [items],
  );

  const PAD = { left: 40, right: 20, top: 20, bottom: 36 };
  const chartW = Math.min(width - 32, 800);
  const chartH = 280;
  const innerW = chartW - PAD.left - PAD.right;
  const innerH = chartH - PAD.top - PAD.bottom;

  const maxVal = 21;
  const xScale = (v: number) => PAD.left + (v / maxVal) * innerW;
  const yScale = (v: number) => PAD.top + innerH - (v / maxVal) * innerH;
  const rScale = (js: number) => Math.max(6, Math.min(20, Math.sqrt(js || 1) * 4));

  const gridLines = [0, 3, 5, 8, 13, 21];

  return (
    <div style={{ position: 'relative', padding: '8px 16px' }}>
      <svg width={chartW} height={chartH} style={{ overflow: 'visible' }}>
        {gridLines.map(v => (
          <g key={v}>
            <line x1={xScale(v)} y1={PAD.top} x2={xScale(v)} y2={PAD.top + innerH}
              stroke="#e2e8f0" strokeDasharray="3,3" />
            <line x1={PAD.left} y1={yScale(v)} x2={PAD.left + innerW} y2={yScale(v)}
              stroke="#e2e8f0" strokeDasharray="3,3" />
            <text x={xScale(v)} y={PAD.top + innerH + 16} textAnchor="middle"
              fontSize={10} fill="#8892a8">{v}</text>
            <text x={PAD.left - 6} y={yScale(v) + 4} textAnchor="end"
              fontSize={10} fill="#8892a8">{v}</text>
          </g>
        ))}
        <text x={PAD.left + innerW / 2} y={chartH - 2} textAnchor="middle"
          fontSize={11} fill="#64748b" fontWeight={600}>
          BV (Business Value →)
        </text>
        <text x={10} y={PAD.top + innerH / 2} textAnchor="middle"
          fontSize={11} fill="#64748b" fontWeight={600}
          transform={`rotate(-90, 10, ${PAD.top + innerH / 2})`}>
          TC ↑
        </text>

        {chartItems.map(item => {
          const cx = xScale(item.bv ?? 0);
          const cy = yScale(item.tc ?? 0);
          const r = rScale(item.js ?? 1);
          const color = statusColor(item.status || '');
          const isDone = DONE_STATUSES.has((item.status || '').toLowerCase());
          return (
            <g key={item.id}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setTooltip(
                `${item.id} — ${item.title}\nBV:${item.bv ?? '-'}  TC:${item.tc ?? '-'}  RR:${item.rr ?? '-'}  JS:${item.js ?? '-'}  WSJF:${item.wsjf?.toFixed(2) ?? '-'}\n${item.status}`
              )}
              onMouseLeave={() => setTooltip(null)}>
              <circle cx={cx} cy={cy} r={r}
                fill={color} fillOpacity={isDone ? 0.35 : 0.7}
                stroke={color} strokeWidth={1.5} />
              {r >= 10 && (
                <text x={cx} y={cy + 4}
                  textAnchor="middle" fontSize={9} fill="#fff" fontWeight={700}
                  style={{ pointerEvents: 'none' }}>
                  {item.id.split('-')[1] ?? item.id}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748b', marginTop: 2 }}>
        {[['#059669', 'Done'], ['#2563eb', 'Implementing'], ['#d97706', 'Validating'], ['#8892a8', 'Other']].map(
          ([c, l]) => (
            <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: c, display: 'inline-block' }} />
              {l}
            </span>
          ),
        )}
        <span style={{ marginLeft: 8 }}>● size = JS</span>
      </div>

      {tooltip && (
        <div style={{
          position: 'absolute', top: 0, right: 0,
          background: '#1e293b', color: '#f1f5f9',
          borderRadius: 6, padding: '8px 12px', fontSize: 11,
          whiteSpace: 'pre', zIndex: 10, pointerEvents: 'none',
          maxWidth: 280, lineHeight: 1.6,
        }}>
          {tooltip}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function PrioritizationSection({ items: rawItems, pi: rawPi, width }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;
  const [sortBy, setSortBy] = useState<SortKey>('wsjf');
  const [sortAsc, setSortAsc] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('table');

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
  const si = (key: SortKey) => sortBy === key ? (sortAsc ? ' ▲' : ' ▼') : '';

  return (
    <div className="prio-section" style={{ width }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px' }}>
        <span style={{ fontSize: 11, color: '#8892a8' }}>{features.length} features</span>
        <div className="prio-view-toggle">
          <button
            className={'prio-toggle-btn' + (viewMode === 'table' ? ' prio-toggle-btn--active' : '')}
            onClick={() => setViewMode('table')}>
            Table
          </button>
          <button
            className={'prio-toggle-btn' + (viewMode === 'bubble' ? ' prio-toggle-btn--active' : '')}
            onClick={() => setViewMode('bubble')}>
            Bubble ●
          </button>
        </div>
      </div>

      {viewMode === 'bubble' ? (
        <WsjfBubbleChart items={features} width={width} />
      ) : (
        <table className="prio-section__table">
          <thead>
            <tr>
              <th>#</th><th>ID</th><th>Title</th>
              <th onClick={() => toggleSort('bv')} style={{ cursor: 'pointer' }}>BV{si('bv')}</th>
              <th onClick={() => toggleSort('tc')} style={{ cursor: 'pointer' }}>TC{si('tc')}</th>
              <th onClick={() => toggleSort('rr')} style={{ cursor: 'pointer' }}>RR{si('rr')}</th>
              <th onClick={() => toggleSort('js')} style={{ cursor: 'pointer' }}>JS{si('js')}</th>
              <th onClick={() => toggleSort('wsjf')} style={{ cursor: 'pointer' }}>WSJF{si('wsjf')}</th>
              <th>Status</th><th>Owner</th>
            </tr>
          </thead>
          <tbody>
            {features.map((item, idx) => (
              <tr key={item.id} style={{ opacity: DONE_STATUSES.has((item.status || '').toLowerCase()) ? 0.45 : 1 }}>
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
      )}
    </div>
  );
}
