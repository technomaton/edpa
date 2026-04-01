import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { WorkItem } from '../../types/edpa';

const TYPE_COLORS: Record<string, { border: string; bg: string }> = {
  Initiative: { border: '#db2777', bg: 'rgba(219,39,119,0.08)' },
  Epic:       { border: '#6366f1', bg: 'rgba(99,102,241,0.08)' },
  Feature:    { border: '#0891b2', bg: 'rgba(8,145,178,0.08)' },
  Story:      { border: '#ea580c', bg: 'rgba(234,88,12,0.08)' },
  Defect:     { border: '#dc2626', bg: 'rgba(220,38,38,0.08)' },
};

function FeatureCardInner({ data }: NodeProps) {
  const item = data.item as WorkItem;
  const colors = TYPE_COLORS[item.type] || TYPE_COLORS.Feature;
  const isDone = item.status === 'Done';

  return (
    <div
      className="feature-card"
      style={{
        borderLeftColor: colors.border,
        backgroundColor: colors.bg,
        opacity: isDone ? 0.55 : 1,
      }}
    >
      <Handle type="target" position={Position.Left} className="feature-card__handle" />
      <Handle type="source" position={Position.Right} className="feature-card__handle" />
      <div className="feature-card__head">
        <span className="feature-card__id" style={{ color: colors.border }}>
          {item.id}
        </span>
        {item.js != null && (
          <span className="feature-card__js">JS {item.js}</span>
        )}
      </div>
      <div className="feature-card__title">{item.title}</div>
      {item.wsjf != null && (
        <div className="feature-card__wsjf">
          {item.bv != null && <span className="wsjf-bv">BV {item.bv}</span>}
          {item.tc != null && <span className="wsjf-tc">TC {item.tc}</span>}
          {item.rr != null && <span className="wsjf-rr">RR {item.rr}</span>}
        </div>
      )}
      <div className="feature-card__foot">
        <span className="feature-card__owner">{item.owner || item.assignee || '-'}</span>
        <span className="feature-card__status">{item.status}</span>
      </div>
    </div>
  );
}

export const FeatureCard = memo(FeatureCardInner);
