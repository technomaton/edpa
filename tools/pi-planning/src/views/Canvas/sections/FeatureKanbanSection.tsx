import { useMemo } from 'react';
import type { WorkItem, KanbanColumnConfig } from '../../../types/edpa';

interface Props {
  items: unknown[];
  selectedPI: string | null;
  isReadonly: boolean;
  width: number;
  height: number;
}

const COLUMNS: KanbanColumnConfig[] = [
  { status: 'Funnel', label: 'Funnel' },
  { status: 'Analyzing', label: 'Analyzing' },
  { status: 'Backlog', label: 'Backlog' },
  { status: 'Implementing', label: 'Implementing' },
  { status: 'Validating', label: 'Validating' },
  { status: 'Deploying', label: 'Deploying' },
  { status: 'Releasing', label: 'Releasing' },
  { status: 'Done', label: 'Done' },
];

export function FeatureKanbanSection({ items: rawItems, selectedPI, width }: Props) {
  const items = rawItems as WorkItem[];

  const features = useMemo(
    () => items.filter(i => {
      if (i.type !== 'Feature') return false;
      if (!selectedPI) return true;
      if (!i.iteration) return true;
      return i.iteration.startsWith(selectedPI);
    }),
    [items, selectedPI],
  );

  const byStatus = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    for (const col of COLUMNS) map[col.status] = [];
    for (const item of features) {
      const key = item.status;
      if (map[key]) map[key].push(item);
      else if (map['Funnel']) map['Funnel'].push(item);
    }
    return map;
  }, [features]);

  return (
    <div className="kanban-section" style={{ width }}>
      <div className="kanban-section__columns">
        {COLUMNS.map(col => {
          const colItems = byStatus[col.status] || [];
          return (
            <div key={col.status} className="kanban-section__col">
              <div className="kanban-section__col-header">
                <span>{col.label}</span>
                <span className="kanban-section__col-count">{colItems.length}</span>
              </div>
              <div className="kanban-section__col-body">
                {colItems.map(item => (
                  <div key={item.id} className="kanban-section__card" style={{ borderLeftColor: '#0891b2' }}>
                    <div className="kanban-section__card-head">
                      <span className="kanban-section__card-id" style={{ color: '#0891b2' }}>{item.id}</span>
                    </div>
                    <span className="kanban-section__card-title">{item.title}</span>
                    {item.iteration && <span className="kanban-section__card-iter">{item.iteration}</span>}
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
