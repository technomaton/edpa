import { useMemo } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, KanbanColumnConfig } from '../../types/edpa';
import { KanbanBoard } from '../../components/KanbanBoard/KanbanBoard';

const INITIATIVE_COLUMNS: KanbanColumnConfig[] = [
  { status: 'Funnel', label: 'Funnel' },
  { status: 'Reviewing', label: 'Reviewing', wipLimit: 3 },
  { status: 'Analyzing', label: 'Analyzing', wipLimit: 3 },
  { status: 'Ready', label: 'Ready' },
  {
    status: 'Implementing', label: 'Implementing',
    subColumns: [
      { key: 'MVP', label: 'MVP' },
      { key: 'Persevere', label: 'Persevere' },
    ],
  },
  { status: 'Done', label: 'Done' },
];

export function InitiativeKanban() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const isReadonly = useConfigStore(s => s.isReadonly);

  const initiatives = useMemo(
    () => items.filter(i => i.type === 'Initiative'),
    [items],
  );

  const getItemColumn = (item: WorkItem) => {
    if (item.status === 'Implementing' && item.implementing_phase) {
      return `Implementing:${item.implementing_phase}`;
    }
    return item.status;
  };

  const handleStatusChange = (itemId: string, newStatus: string, subColumn?: string) => {
    const changes: Partial<WorkItem> = { status: newStatus as WorkItem['status'] };
    if (newStatus === 'Implementing' && subColumn) {
      changes.implementing_phase = subColumn as 'MVP' | 'Persevere';
    } else {
      changes.implementing_phase = undefined;
    }
    updateItem(itemId, changes);
    saveItem(itemId);
  };

  return (
    <KanbanBoard
      title="Initiative Kanban"
      subtitle="Portfolio Kanban — SAFe 6"
      columns={INITIATIVE_COLUMNS}
      items={initiatives}
      onStatusChange={handleStatusChange}
      getItemColumn={getItemColumn}
      readonly={isReadonly}
    />
  );
}
