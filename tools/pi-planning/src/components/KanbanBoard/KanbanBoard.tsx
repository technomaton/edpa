import { useMemo, type ReactNode } from 'react';
import type { WorkItem, KanbanColumnConfig } from '../../types/edpa';
import { KanbanColumn } from './KanbanColumn';
import { KanbanCard } from './KanbanCard';

interface KanbanBoardProps {
  title: string;
  subtitle?: string;
  columns: KanbanColumnConfig[];
  items: WorkItem[];
  onStatusChange: (itemId: string, newStatus: string, subColumn?: string) => void;
  onCardClick?: (item: WorkItem) => void;
  readonly?: boolean;
  renderCard?: (item: WorkItem) => ReactNode;
  getItemColumn?: (item: WorkItem) => string;
}

export function KanbanBoard({
  title, subtitle, columns, items, onStatusChange,
  onCardClick, readonly, renderCard, getItemColumn,
}: KanbanBoardProps) {
  const itemsByColumn = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    for (const col of columns) {
      map[col.status] = [];
      if (col.subColumns) {
        for (const sub of col.subColumns) {
          map[`${col.status}:${sub.key}`] = [];
        }
      }
    }
    for (const item of items) {
      const colKey = getItemColumn ? getItemColumn(item) : item.status;
      if (map[colKey]) {
        map[colKey].push(item);
      } else if (map[item.status]) {
        map[item.status].push(item);
      }
    }
    return map;
  }, [columns, items, getItemColumn]);

  const totalByStatus = useMemo(() => {
    const map: Record<string, number> = {};
    for (const col of columns) {
      let count = (itemsByColumn[col.status] || []).length;
      if (col.subColumns) {
        for (const sub of col.subColumns) {
          count += (itemsByColumn[`${col.status}:${sub.key}`] || []).length;
        }
      }
      map[col.status] = count;
    }
    return map;
  }, [columns, itemsByColumn]);

  const card = (item: WorkItem) =>
    renderCard ? renderCard(item) : <KanbanCard key={item.id} item={item} onClick={onCardClick} />;

  return (
    <div className="kanban-board">
      <div className="kanban-board__header">
        <h2 className="kanban-board__title">{title}</h2>
        {subtitle && <span className="kanban-board__sub">{subtitle}</span>}
        <span className="kanban-board__total">{items.length} items</span>
      </div>
      <div className="kanban-board__columns">
        {columns.map(col => {
          const colItems = itemsByColumn[col.status] || [];
          return (
            <KanbanColumn
              key={col.status}
              status={col.status}
              label={col.label}
              count={totalByStatus[col.status] || 0}
              wipLimit={col.wipLimit}
              subColumns={col.subColumns}
              onDrop={onStatusChange}
              readonly={readonly}
            >
              {col.subColumns
                ? col.subColumns.map(sub => {
                    const subItems = itemsByColumn[`${col.status}:${sub.key}`] || [];
                    return subItems.map(item => card(item));
                  })
                : colItems.map(item => card(item))
              }
            </KanbanColumn>
          );
        })}
      </div>
    </div>
  );
}
