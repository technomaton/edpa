import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { WorkItem } from '../../types/edpa';

const TYPE_COLORS: Record<string, { border: string; fg: string }> = {
  Initiative: { border: '#db2777', fg: '#db2777' },
  Epic:       { border: '#6366f1', fg: '#6366f1' },
  Feature:    { border: '#0891b2', fg: '#0891b2' },
  Story:      { border: '#ea580c', fg: '#ea580c' },
  Defect:     { border: '#dc2626', fg: '#dc2626' },
};

function FeatureCardInner({ data }: NodeProps) {
  const item = data.item as WorkItem;
  const onSelect = data.onSelect as ((item: WorkItem) => void) | undefined;
  const colors = TYPE_COLORS[item.type] || TYPE_COLORS.Feature;
  const isDone = item.status === 'Done';

  return (
    <div
      className={`rf-card ${isDone ? 'rf-card--done' : ''}`}
      style={{ borderLeftColor: colors.border }}
      onClick={(e) => { e.stopPropagation(); onSelect?.(item); }}
    >
      <Handle type="target" position={Position.Left} className="rf-card__handle" />
      <Handle type="source" position={Position.Right} className="rf-card__handle" />
      <div className="rf-card__head">
        <span className="rf-card__id" style={{ color: colors.fg }}>{item.id}</span>
        {item.js != null && <span className="rf-card__js">JS {item.js}</span>}
        {item.wsjf != null && <span className="rf-card__wsjf">W {item.wsjf.toFixed(1)}</span>}
      </div>
      <div className="rf-card__title">{item.title}</div>
      <div className="rf-card__foot">
        <span className="rf-card__owner">{item.owner || item.assignee || ''}</span>
        <span className="rf-card__status">{item.status}</span>
      </div>
    </div>
  );
}

export const FeatureCard = memo(FeatureCardInner);
