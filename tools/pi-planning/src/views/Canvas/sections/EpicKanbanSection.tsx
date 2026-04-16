import { useMemo } from 'react';
import type { WorkItem, KanbanColumnConfig } from '../../../types/edpa';

interface Props {
  items: unknown[];
  isReadonly: boolean;
  width: number;
  height: number;
}

const COLUMNS: KanbanColumnConfig[] = [
  { status: 'Funnel', label: 'Funnel' },
  { status: 'Reviewing', label: 'Reviewing', wipLimit: 3 },
  { status: 'Analyzing', label: 'Analyzing', wipLimit: 3 },
  { status: 'Ready', label: 'Ready' },
  { status: 'Implementing', label: 'Implementing' },
  { status: 'Done', label: 'Done' },
];

const TYPE_FG: Record<string, string> = {
  Initiative: '#db2777', Epic: '#6366f1',
};

export function EpicKanbanSection({ items: rawItems, width }: Props) {
  const items = rawItems as WorkItem[];

  const epics = useMemo(
    () => items.filter(i => i.type === 'Epic'),
    [items],
  );

  const byStatus = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    for (const col of COLUMNS) map[col.status] = [];
    for (const item of epics) {
      const key = item.status;
      if (map[key]) map[key].push(item);
      else if (map['Funnel']) map['Funnel'].push(item);
    }
    return map;
  }, [epics]);

  return (
    <div className="kanban-section" style={{ width }}>
      <div className="kanban-section__columns">
        {COLUMNS.map(col => {
          const colItems = byStatus[col.status] || [];
          const overWip = col.wipLimit != null && colItems.length > col.wipLimit;
          return (
            <div key={col.status} className="kanban-section__col">
              <div className={`kanban-section__col-header ${overWip ? 'kanban-section__col-header--over-wip' : ''}`}>
                <span>{col.label}</span>
                <span className="kanban-section__col-count">
                  {colItems.length}{col.wipLimit != null ? `/${col.wipLimit}` : ''}
                </span>
              </div>
              <div className="kanban-section__col-body">
                {colItems.map(item => (
                  <div key={item.id} className="kanban-section__card" style={{ borderLeftColor: TYPE_FG[item.type] || '#6366f1' }}>
                    <div className="kanban-section__card-head">
                      <span className="kanban-section__card-id" style={{ color: TYPE_FG[item.type] }}>{item.id}</span>
                      {item.epic_type && <span className="kanban-section__card-badge">{item.epic_type}</span>}
                    </div>
                    <span className="kanban-section__card-title">{item.title}</span>
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
