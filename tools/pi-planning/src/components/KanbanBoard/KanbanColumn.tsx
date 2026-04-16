import { useState, type DragEvent, type ReactNode } from 'react';

interface KanbanColumnProps {
  status: string;
  label: string;
  count: number;
  wipLimit?: number;
  subColumns?: { key: string; label: string }[];
  onDrop: (itemId: string, status: string, subColumn?: string) => void;
  readonly?: boolean;
  children: ReactNode;
}

export function KanbanColumn({
  status, label, count, wipLimit, subColumns, onDrop, readonly, children,
}: KanbanColumnProps) {
  const [dragOver, setDragOver] = useState<string | null>(null);
  const overWip = wipLimit != null && count > wipLimit;

  const handleDragOver = (e: DragEvent, sub?: string) => {
    if (readonly) return;
    e.preventDefault();
    setDragOver(sub ?? status);
  };

  const handleDrop = (e: DragEvent, sub?: string) => {
    e.preventDefault();
    setDragOver(null);
    if (readonly) return;
    const id = e.dataTransfer.getData('text/plain');
    if (id) onDrop(id, status, sub);
  };

  if (subColumns && subColumns.length > 0) {
    return (
      <div className="kanban-col kanban-col--parent">
        <div className={`kanban-col__header ${overWip ? 'kanban-col__header--over-wip' : ''}`}>
          <span className="kanban-col__label">{label}</span>
          <span className="kanban-col__count">
            {count}{wipLimit != null ? `/${wipLimit}` : ''}
          </span>
        </div>
        <div className="kanban-col__subs">
          {subColumns.map(sub => (
            <div
              key={sub.key}
              className={`kanban-col__sub ${dragOver === sub.key ? 'kanban-col--drag-over' : ''}`}
              onDragOver={e => handleDragOver(e, sub.key)}
              onDragLeave={() => setDragOver(null)}
              onDrop={e => handleDrop(e, sub.key)}
            >
              <div className="kanban-col__sub-label">{sub.label}</div>
              <div className="kanban-col__body">
                {children}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`kanban-col ${dragOver ? 'kanban-col--drag-over' : ''}`}
      onDragOver={e => handleDragOver(e)}
      onDragLeave={() => setDragOver(null)}
      onDrop={e => handleDrop(e)}
    >
      <div className={`kanban-col__header ${overWip ? 'kanban-col__header--over-wip' : ''}`}>
        <span className="kanban-col__label">{label}</span>
        <span className="kanban-col__count">
          {count}{wipLimit != null ? `/${wipLimit}` : ''}
        </span>
      </div>
      <div className="kanban-col__body">
        {children}
      </div>
    </div>
  );
}
