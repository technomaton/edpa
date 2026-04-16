import { useMemo } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, KanbanColumnConfig } from '../../types/edpa';
import { KanbanBoard } from '../../components/KanbanBoard/KanbanBoard';

const FEATURE_COLUMNS: KanbanColumnConfig[] = [
  { status: 'Funnel', label: 'Funnel' },
  { status: 'Analyzing', label: 'Analyzing' },
  { status: 'Backlog', label: 'Backlog' },
  { status: 'Implementing', label: 'Implementing' },
  { status: 'Validating', label: 'Validating' },
  { status: 'Deploying', label: 'Deploying' },
  { status: 'Releasing', label: 'Releasing' },
  { status: 'Done', label: 'Done' },
];

export function FeatureKanban() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const isReadonly = useConfigStore(s => s.isReadonly);

  const features = useMemo(
    () => items.filter(i => {
      if (i.type !== 'Feature') return false;
      if (!selectedPI) return true;
      if (!i.iteration) return true;
      return i.iteration.startsWith(selectedPI);
    }),
    [items, selectedPI],
  );

  const handleStatusChange = (itemId: string, newStatus: string) => {
    updateItem(itemId, { status: newStatus as WorkItem['status'] });
    saveItem(itemId);
  };

  return (
    <KanbanBoard
      title="Feature Kanban"
      subtitle="Delivery Kanban — SAFe 6"
      columns={FEATURE_COLUMNS}
      items={features}
      onStatusChange={handleStatusChange}
      readonly={isReadonly}
    />
  );
}
