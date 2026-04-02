import { useMemo, useState, type DragEvent } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, RoamStatus, Severity } from '../../types/edpa';
import { api } from '../../lib/api';

const ROAM_COLUMNS: { status: RoamStatus; label: string }[] = [
  { status: 'resolved', label: 'Resolved' },
  { status: 'owned', label: 'Owned' },
  { status: 'accepted', label: 'Accepted' },
  { status: 'mitigated', label: 'Mitigated' },
];

const SEVERITY_COLORS: Record<Severity, string> = {
  high: '#dc2626',
  medium: '#d97706',
  low: '#059669',
};

function RiskCard({ item }: { item: WorkItem }) {
  const severity = item.severity || 'medium';

  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className="roam-card"
      draggable
      onDragStart={onDragStart}
      style={{ borderLeftColor: SEVERITY_COLORS[severity] }}
    >
      <div className="roam-card__head">
        <span className="roam-card__id">{item.id}</span>
        <span
          className="roam-card__severity"
          style={{ background: SEVERITY_COLORS[severity] }}
        >
          {severity}
        </span>
      </div>
      <div className="roam-card__title">{item.title}</div>
      <div className="roam-card__foot">
        <span className="roam-card__owner">{item.owner || '-'}</span>
        <span className="roam-card__iter">{item.iteration || '-'}</span>
      </div>
    </div>
  );
}

function RoamColumn({
  status,
  label,
  items,
  onDrop,
}: {
  status: RoamStatus;
  label: string;
  items: WorkItem[];
  onDrop: (itemId: string, status: RoamStatus) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <div
      className={`roam-column roam-column--${status} ${dragOver ? 'roam-column--drag-over' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault();
        setDragOver(false);
        const id = e.dataTransfer.getData('text/plain');
        if (id) onDrop(id, status);
      }}
    >
      <div className={`roam-column__header roam-column__header--${status}`}>
        <span className="roam-column__label">{label}</span>
        <span className="roam-column__count">{items.length}</span>
      </div>
      <div className="roam-column__body">
        {items.map(item => <RiskCard key={item.id} item={item} />)}
      </div>
    </div>
  );
}

export function ROAM() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const fetchBacklog = useBacklogStore(s => s.fetch);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const isReadonly = useConfigStore(s => s.isReadonly);

  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newSeverity, setNewSeverity] = useState<Severity>('medium');

  const risks = useMemo(() => {
    return items.filter(i => {
      if (i.type !== 'Risk') return false;
      if (!selectedPI) return true;
      if (!i.iteration) return true;
      return i.iteration.startsWith(selectedPI);
    });
  }, [items, selectedPI]);

  const handleDrop = (itemId: string, roamStatus: RoamStatus) => {
    if (isReadonly) return;
    updateItem(itemId, { roam_status: roamStatus });
    saveItem(itemId);
  };

  const handleAddRisk = async () => {
    if (!newTitle.trim()) return;
    const risk: Partial<WorkItem> = {
      title: newTitle.trim(),
      roam_status: 'owned',
      severity: newSeverity,
      status: 'Active',
      js: 0,
      contributors: [],
      parent: null,
      iteration: selectedPI ? `${selectedPI}.1` : undefined,
    };
    await api.createItem('risks', risk);
    setNewTitle('');
    setAdding(false);
    fetchBacklog();
  };

  return (
    <div className="roam-container">
      <div className="roam-header">
        <h2 className="roam-header__title">ROAM Board</h2>
        <span className="roam-header__sub">Risks, Obstacles, Assumptions, Mitigations</span>
        {!isReadonly && (
          <button className="roam-add-btn" onClick={() => setAdding(true)}>
            + Add Risk
          </button>
        )}
      </div>

      {adding && (
        <div className="roam-add-form">
          <input
            className="roam-add-form__input"
            placeholder="Risk title..."
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAddRisk()}
            autoFocus
          />
          <select
            className="roam-add-form__select"
            value={newSeverity}
            onChange={e => setNewSeverity(e.target.value as Severity)}
          >
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <button className="roam-add-form__ok" onClick={handleAddRisk}>Create</button>
          <button className="roam-add-form__cancel" onClick={() => setAdding(false)}>Cancel</button>
        </div>
      )}

      <div className="roam-board">
        {ROAM_COLUMNS.map(col => (
          <RoamColumn
            key={col.status}
            status={col.status}
            label={col.label}
            items={risks.filter(r => r.roam_status === col.status)}
            onDrop={handleDrop}
          />
        ))}
      </div>
    </div>
  );
}
