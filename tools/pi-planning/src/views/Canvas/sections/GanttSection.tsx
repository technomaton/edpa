import { useMemo } from 'react';
import type { WorkItem, PIConfig } from '../../../types/edpa';

interface Props {
  items: unknown[];
  pi: unknown;
  width: number;
  height: number;
}

const DONE_STATUSES = new Set(['done', 'closed', 'accepted', 'complete', 'completed']);
const ROW_H = 30;
const HEADER_H = 36;
const LABEL_W = 110;
const PAD = 20;

export function GanttSection({ items: rawItems, pi: rawPi, width, height }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;

  const iterations = useMemo(() => pi?.iterations || [], [pi]);

  const features = useMemo(() => {
    if (!pi) return [];
    const piId = pi.id;
    return items.filter(
      i => i.type === 'Feature' &&
        (!i.iteration || i.iteration === piId || i.iteration.startsWith(piId + '.')),
    );
  }, [items, pi]);

  // storyMap[featureId][iterationId] = { total, done }
  const storyMap = useMemo(() => {
    const map: Record<string, Record<string, { total: number; done: number }>> = {};
    for (const f of features) {
      map[f.id] = {};
      for (const it of iterations) map[f.id][it.id] = { total: 0, done: 0 };
    }
    for (const s of items) {
      if (s.type !== 'Story' || !s.parent) continue;
      const cell = map[s.parent]?.[s.iteration ?? ''];
      if (!cell) continue;
      cell.total += 1;
      if (DONE_STATUSES.has((s.status || '').toLowerCase())) cell.done += 1;
    }
    return map;
  }, [features, iterations, items]);

  if (!pi || features.length === 0) {
    return (
      <div style={{ padding: 16, color: '#8892a8', fontSize: 13 }}>
        No features assigned to PI {pi?.id ?? '…'}
      </div>
    );
  }

  const maxCols = Math.max(1, iterations.length);
  const colW = Math.max(60, Math.floor((width - LABEL_W - PAD * 2) / maxCols));
  const svgW = LABEL_W + colW * maxCols + PAD;
  const svgH = HEADER_H + features.length * ROW_H + 8;

  return (
    <div className="gantt-wrap" style={{ width, height, overflow: 'auto' }}>
      <div className="gantt-header-row">
        <span className="gantt-title">Feature Gantt — {pi.id}</span>
        <span className="gantt-sub">{features.length} features · {iterations.length} iterations</span>
      </div>
      <svg width={svgW} height={svgH} className="gantt-svg">
        {/* ─── iteration header ─────────────────── */}
        {iterations.map((iter, ci) => {
          const x = LABEL_W + ci * colW;
          const isActive = iter.status === 'active';
          return (
            <g key={iter.id}>
              <rect x={x} y={0} width={colW} height={HEADER_H}
                fill={isActive ? '#eff6ff' : '#f8fafc'} stroke="#e2e8f0" />
              {isActive && <rect x={x} y={0} width={colW} height={3} fill="#3b82f6" />}
              <text x={x + colW / 2} y={HEADER_H / 2 + 5}
                textAnchor="middle" className="gantt-iter-label">
                {/* show ".3" instead of "PI-2026-1.3" */}
                {iter.id.includes('.') ? '.' + iter.id.split('.').pop() : iter.id}
              </text>
            </g>
          );
        })}

        {/* ─── feature rows ─────────────────────── */}
        {features.map((feat, ri) => {
          const rowY = HEADER_H + ri * ROW_H;
          const isDone = DONE_STATUSES.has((feat.status || '').toLowerCase());
          return (
            <g key={feat.id}>
              <rect x={0} y={rowY} width={svgW} height={ROW_H}
                fill={ri % 2 === 0 ? '#fff' : '#f8fafc'} />
              {/* feature label */}
              <text x={6} y={rowY + ROW_H / 2 + 5} className="gantt-feat-id"
                fill={isDone ? '#059669' : '#0891b2'}>
                {feat.id}
              </text>

              {/* iteration cells */}
              {iterations.map((iter, ci) => {
                const cell = storyMap[feat.id]?.[iter.id] ?? { total: 0, done: 0 };
                const bx = LABEL_W + ci * colW + 3;
                const bw = colW - 6;
                const bh = ROW_H - 8;
                const by = rowY + 4;
                const pct = cell.total > 0 ? cell.done / cell.total : 0;
                const baseFill = isDone ? '#a7f3d0' : cell.total > 0 ? '#bfdbfe' : '#f1f5f9';
                const doneFill = isDone ? '#059669' : '#2563eb';
                return (
                  <g key={iter.id}>
                    <rect x={bx} y={by} width={bw} height={bh}
                      fill={baseFill} rx={3} stroke="#e2e8f0" />
                    {cell.total > 0 && pct > 0 && (
                      <rect x={bx} y={by} width={Math.round(bw * pct)} height={bh}
                        fill={doneFill} rx={3} />
                    )}
                    {cell.total > 0 && (
                      <text x={bx + bw / 2} y={by + bh / 2 + 4}
                        textAnchor="middle" className="gantt-cell-label">
                        {cell.done}/{cell.total}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}

        {/* ─── column dividers ──────────────────── */}
        {iterations.map((_, ci) => (
          <line key={ci}
            x1={LABEL_W + ci * colW} y1={HEADER_H}
            x2={LABEL_W + ci * colW} y2={svgH}
            stroke="#e2e8f0" strokeDasharray="2,2" />
        ))}
      </svg>
    </div>
  );
}
