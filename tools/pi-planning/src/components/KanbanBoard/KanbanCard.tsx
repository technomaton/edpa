import type { DragEvent } from 'react';
import type { WorkItem } from '../../types/edpa';

const TYPE_FG: Record<string, string> = {
  Initiative: '#db2777', Epic: '#6366f1', Feature: '#0891b2',
  Story: '#ea580c', Defect: '#dc2626',
};

interface KanbanCardProps {
  item: WorkItem;
  onClick?: (item: WorkItem) => void;
}

export function KanbanCard({ item, onClick }: KanbanCardProps) {
  const color = TYPE_FG[item.type] || '#64748b';

  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const wsjf = item.wsjf != null ? item.wsjf.toFixed(1) : null;

  return (
    <div
      className="kanban-card"
      draggable
      onDragStart={onDragStart}
      onClick={() => onClick?.(item)}
      style={{ borderLeftColor: color }}
    >
      <div className="kanban-card__head">
        <span className="kanban-card__id" style={{ color }}>{item.id}</span>
        <span className="kanban-card__type" style={{ background: color }}>{item.type}</span>
      </div>
      <div className="kanban-card__title">{item.title}</div>
      <div className="kanban-card__foot">
        <span className="kanban-card__owner">{item.owner || item.assignee || '-'}</span>
        {item.epic_type && (
          <span className={`kanban-card__epic-type kanban-card__epic-type--${item.epic_type.toLowerCase()}`}>
            {item.epic_type}
          </span>
        )}
        {wsjf && <span className="kanban-card__wsjf">WSJF {wsjf}</span>}
        {item.js > 0 && <span className="kanban-card__js">JS {item.js}</span>}
      </div>
      {item.iteration && (
        <div className="kanban-card__iter">{item.iteration}</div>
      )}
    </div>
  );
}
