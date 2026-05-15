import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { WorkItem } from '../../types/edpa';

// Dependency-based color coding (SAFe convention):
// blue = independent (no incoming dependencies)
// red = dependent (has incoming dependencies from other items)
// yellow/orange = event (release, demo, deadline, etc.)
const DEP_COLORS: Record<string, { border: string; bg: string; fg: string }> = {
  independent: { border: '#2563eb', bg: 'rgba(37,99,235,0.06)', fg: '#2563eb' },
  dependent:   { border: '#dc2626', bg: 'rgba(220,38,38,0.06)', fg: '#dc2626' },
  event:       { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)', fg: '#d97706' },
};

function FeatureCardInner({ data }: NodeProps) {
  const item = data.item as WorkItem;
  const onSelect = data.onSelect as ((item: WorkItem) => void) | undefined;
  const depColor = (data.depColor as string) || 'independent';
  const colors = DEP_COLORS[depColor] || DEP_COLORS.independent;
  const isDone = item.status === 'Done';
  const isEvent = item.type === 'Event';

  return (
    <div
      className={`rf-card rf-card--${depColor} ${isDone ? 'rf-card--done' : ''}`}
      style={{ borderLeftColor: colors.border, backgroundColor: colors.bg }}
      onClick={(e) => { e.stopPropagation(); onSelect?.(item); }}
    >
      <Handle type="target" position={Position.Left} className="rf-card__handle" />
      <Handle type="source" position={Position.Right} className="rf-card__handle" />
      <div className="rf-card__head">
        <span className="rf-card__id" style={{ color: colors.fg }}>{item.id}</span>
        {!isEvent && item.js != null && <span className="rf-card__js">JS {item.js}</span>}
        {!isEvent && item.wsjf != null && <span className="rf-card__wsjf">W {item.wsjf.toFixed(1)}</span>}
      </div>
      <div className="rf-card__title">{item.title}</div>
      <div className="rf-card__foot">
        <span className="rf-card__owner">{item.owner || item.assignee || ''}</span>
        <span className="rf-card__status">{isEvent ? item.type : item.status}</span>
      </div>
    </div>
  );
}

export const FeatureCard = memo(FeatureCardInner);
