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

export function InitiativeKanbanSection({ items: rawItems, width }: Props) {
  const items = rawItems as WorkItem[];

  const initiatives = useMemo(
    () => items.filter(i => i.type === 'Initiative'),
    [items],
  );

  const byStatus = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    for (const col of COLUMNS) map[col.status] = [];
    for (const item of initiatives) {
      const key = item.status;
      if (map[key]) map[key].push(item);
      else if (map['Funnel']) map['Funnel'].push(item);
    }
    return map;
  }, [initiatives]);

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
                  <div key={item.id} className="kanban-section__card" style={{ borderLeftColor: '#db2777' }}>
                    <div className="kanban-section__card-head">
                      <span className="kanban-section__card-id" style={{ color: '#db2777' }}>{item.id}</span>
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
