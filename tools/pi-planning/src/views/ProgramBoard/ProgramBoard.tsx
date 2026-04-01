import { Fragment, useMemo, useState, useCallback, type DragEvent } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, Person, Iteration } from '../../types/edpa';

// -- Helpers ------------------------------------------------------------------

function getTeamForItem(item: WorkItem, personTeam: Record<string, string>): string {
  return personTeam[item.owner || ''] || personTeam[item.assignee || ''] || 'Unassigned';
}

function iterationForItem(item: WorkItem, iterations: Iteration[]): string | null {
  if (!item.iteration) return null;
  const match = iterations.find(it => item.iteration!.startsWith(it.id));
  return match?.id || null;
}

function capacityForCell(
  teamId: string,
  iterationId: string,
  items: WorkItem[],
  people: Person[],
  personTeam: Record<string, string>,
  planningFactor: number,
): { used: number; available: number } {
  const teamPeople = people.filter(p => p.team === teamId);
  const available = teamPeople.reduce((sum, p) => sum + p.capacity, 0) * planningFactor;
  const cellItems = items.filter(
    i => getTeamForItem(i, personTeam) === teamId &&
         i.iteration?.startsWith(iterationId) &&
         (i.type === 'Feature' || i.type === 'Story'),
  );
  const used = cellItems.reduce((sum, i) => sum + (i.js || 0), 0);
  return { used, available };
}

// -- Card Component -----------------------------------------------------------

const TYPE_COLORS: Record<string, { border: string; bg: string; fg: string }> = {
  Initiative: { border: '#db2777', bg: 'rgba(219,39,119,0.06)', fg: '#db2777' },
  Epic:       { border: '#6366f1', bg: 'rgba(99,102,241,0.06)',  fg: '#6366f1' },
  Feature:    { border: '#0891b2', bg: 'rgba(8,145,178,0.06)',   fg: '#0891b2' },
  Story:      { border: '#ea580c', bg: 'rgba(234,88,12,0.06)',   fg: '#ea580c' },
  Defect:     { border: '#dc2626', bg: 'rgba(220,38,38,0.06)',   fg: '#dc2626' },
};

function BoardCard({ item, onClick }: { item: WorkItem; onClick: () => void }) {
  const colors = TYPE_COLORS[item.type] || TYPE_COLORS.Feature;
  const isDone = item.status === 'Done';

  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className={`board-card ${isDone ? 'board-card--done' : ''}`}
      style={{ borderLeftColor: colors.border, backgroundColor: colors.bg }}
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
    >
      <div className="board-card__head">
        <span className="board-card__id" style={{ color: colors.fg }}>{item.id}</span>
        {item.js != null && <span className="board-card__js">JS {item.js}</span>}
        {item.wsjf != null && (
          <span className="board-card__wsjf" title="WSJF">
            W {item.wsjf.toFixed(1)}
          </span>
        )}
      </div>
      <div className="board-card__title">{item.title}</div>
      <div className="board-card__foot">
        <span className="board-card__owner">{item.owner || item.assignee || ''}</span>
        <span className={`board-card__status board-card__status--${item.status.toLowerCase().replace(' ', '-')}`}>
          {item.status}
        </span>
      </div>
    </div>
  );
}

// -- Cell Component -----------------------------------------------------------

function BoardCell({
  teamId,
  iterationId,
  items,
  capacity,
  onDrop,
  onCardClick,
}: {
  teamId: string;
  iterationId: string;
  items: WorkItem[];
  capacity: { used: number; available: number };
  onDrop: (itemId: string, iterationId: string, teamId: string) => void;
  onCardClick: (item: WorkItem) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(true);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const itemId = e.dataTransfer.getData('text/plain');
    if (itemId) onDrop(itemId, iterationId, teamId);
  };

  const pct = capacity.available > 0 ? Math.min(100, (capacity.used / capacity.available) * 100) : 0;
  const overloaded = pct > 100;

  return (
    <div
      className={`board-cell ${dragOver ? 'board-cell--drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {items.length > 0 && (
        <div className="board-cell__cards">
          {items.map(item => (
            <BoardCard key={item.id} item={item} onClick={() => onCardClick(item)} />
          ))}
        </div>
      )}
      {capacity.available > 0 && (
        <div className="board-cell__capacity">
          <div className="capacity-bar">
            <div
              className={`capacity-bar__fill ${overloaded ? 'capacity-bar__fill--over' : ''}`}
              style={{ width: `${Math.min(100, pct)}%` }}
            />
          </div>
          <span className={`capacity-label ${overloaded ? 'capacity-label--over' : ''}`}>
            {capacity.used}/{capacity.available}
          </span>
        </div>
      )}
    </div>
  );
}

// -- Detail Panel -------------------------------------------------------------

function DetailPanel({ item, onClose }: { item: WorkItem; onClose: () => void }) {
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <span className="detail-panel__id" style={{ color: TYPE_COLORS[item.type]?.fg }}>
          {item.id}
        </span>
        <button className="detail-panel__close" onClick={onClose}>X</button>
      </div>
      <h3 className="detail-panel__title">{item.title}</h3>
      <div className="detail-panel__grid">
        <div className="detail-field">
          <span className="detail-field__label">Type</span>
          <span className="detail-field__value">{item.type}</span>
        </div>
        <div className="detail-field">
          <span className="detail-field__label">Status</span>
          <span className="detail-field__value">{item.status}</span>
        </div>
        <div className="detail-field">
          <span className="detail-field__label">Iteration</span>
          <span className="detail-field__value">{item.iteration || '-'}</span>
        </div>
        <div className="detail-field">
          <span className="detail-field__label">Owner</span>
          <span className="detail-field__value">{item.owner || item.assignee || '-'}</span>
        </div>
        <div className="detail-field">
          <span className="detail-field__label">Job Size</span>
          <span className="detail-field__value">{item.js ?? '-'}</span>
        </div>
        <div className="detail-field">
          <span className="detail-field__label">WSJF</span>
          <span className="detail-field__value">{item.wsjf?.toFixed(2) ?? '-'}</span>
        </div>
        {item.bv != null && (
          <div className="detail-field">
            <span className="detail-field__label">BV / TC / RR</span>
            <span className="detail-field__value">{item.bv} / {item.tc} / {item.rr}</span>
          </div>
        )}
        <div className="detail-field">
          <span className="detail-field__label">Parent</span>
          <span className="detail-field__value">{item.parent || '-'}</span>
        </div>
      </div>
      {item.contributors && item.contributors.length > 0 && (
        <div className="detail-panel__contributors">
          <span className="detail-field__label">Contributors</span>
          {item.contributors.map((c, i) => (
            <div key={i} className="detail-contributor">
              <span>{c.person}</span>
              <span className="detail-contributor__role">{c.role}</span>
              <span className="detail-contributor__cw">CW {c.cw}</span>
            </div>
          ))}
        </div>
      )}
      {item.depends_on && item.depends_on.length > 0 && (
        <div className="detail-panel__deps">
          <span className="detail-field__label">Depends on</span>
          <span>{item.depends_on.join(', ')}</span>
        </div>
      )}
    </div>
  );
}

// -- Unassigned Pool ----------------------------------------------------------

function UnassignedPool({
  items,
  onCardClick,
}: {
  items: WorkItem[];
  onCardClick: (item: WorkItem) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="unassigned-pool">
      <div className="unassigned-pool__header">
        <span className="unassigned-pool__title">Unassigned / Backlog</span>
        <span className="unassigned-pool__count">{items.length}</span>
      </div>
      <div className="unassigned-pool__cards">
        {items.map(item => (
          <BoardCard key={item.id} item={item} onClick={() => onCardClick(item)} />
        ))}
      </div>
    </div>
  );
}

// -- Main Board ---------------------------------------------------------------

export function ProgramBoard() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const pi = useConfigStore(s => s.pi);
  const people = useConfigStore(s => s.people);
  const teams = useConfigStore(s => s.teams);
  const [selectedItem, setSelectedItem] = useState<WorkItem | null>(null);

  const iterations = pi?.iterations || [];
  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const personTeam = useMemo(() => {
    const map: Record<string, string> = {};
    people.forEach(p => { map[p.id] = p.team; });
    return map;
  }, [people]);

  const planningFactors = useMemo(() => {
    const map: Record<string, number> = {};
    teams.forEach(t => { map[t.id] = t.planning_factor; });
    return map;
  }, [teams]);

  // Features and epics for the board
  const boardItems = useMemo(
    () => items.filter(i => i.type === 'Feature' || i.type === 'Epic'),
    [items],
  );

  // Items assigned to iterations
  const assignedItems = useMemo(
    () => boardItems.filter(i => iterationForItem(i, iterations) !== null),
    [boardItems, iterations],
  );

  // Items NOT assigned to any iteration
  const unassignedItems = useMemo(
    () => boardItems.filter(i => iterationForItem(i, iterations) === null),
    [boardItems, iterations],
  );

  // Group items by cell
  const cellItems = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    assignedItems.forEach(item => {
      const iterId = iterationForItem(item, iterations)!;
      const team = getTeamForItem(item, personTeam);
      const key = `${iterId}::${team}`;
      if (!map[key]) map[key] = [];
      map[key].push(item);
    });
    // Sort by WSJF descending within each cell
    Object.values(map).forEach(arr => arr.sort((a, b) => (b.wsjf || 0) - (a.wsjf || 0)));
    return map;
  }, [assignedItems, iterations, personTeam]);

  const handleDrop = useCallback(
    (itemId: string, iterationId: string, _teamId: string) => {
      const item = items.find(i => i.id === itemId);
      if (!item) return;
      if (item.iteration !== iterationId) {
        updateItem(itemId, { iteration: iterationId });
        saveItem(itemId);
      }
    },
    [items, updateItem, saveItem],
  );

  const gridCols = iterations.length;

  return (
    <div className="pb-container">
      <div className="pb-board" style={{ gridTemplateColumns: `120px repeat(${gridCols}, 1fr)` }}>
        {/* Corner */}
        <div className="pb-corner">
          <span className="pb-corner__label">Team / Iteration</span>
        </div>

        {/* Iteration column headers */}
        {iterations.map(iter => (
          <div key={iter.id} className={`pb-col-header ${iter.status === 'active' ? 'pb-col-header--active' : ''}`}>
            <span className="pb-col-header__id">{iter.id.split('.').pop()}</span>
            <span className="pb-col-header__full">{iter.id}</span>
            <span className="pb-col-header__dates">{iter.dates}</span>
            {iter.type && <span className="pb-col-header__type">{iter.type}</span>}
            <span className={`pb-col-header__status pb-col-header__status--${iter.status}`}>
              {iter.status}
            </span>
          </div>
        ))}

        {/* Team rows */}
        {teamIds.map(teamId => (
          <Fragment key={teamId}>
            {/* Row header */}
            <div className="pb-row-header">
              <span className="pb-row-header__name">{teamId}</span>
              <span className="pb-row-header__count">
                {people.filter(p => p.team === teamId).length} members
              </span>
            </div>

            {/* Cells */}
            {iterations.map(iter => {
              const key = `${iter.id}::${teamId}`;
              const cellItemsList = cellItems[key] || [];
              const cap = capacityForCell(
                teamId, iter.id, items, people, personTeam,
                planningFactors[teamId] || 0.8,
              );
              return (
                <BoardCell
                  key={key}
                  teamId={teamId}
                  iterationId={iter.id}
                  items={cellItemsList}
                  capacity={cap}
                  onDrop={handleDrop}
                  onCardClick={setSelectedItem}
                />
              );
            })}
          </Fragment>
        ))}
      </div>

      {/* Unassigned pool */}
      <UnassignedPool items={unassignedItems} onCardClick={setSelectedItem} />

      {/* Detail panel */}
      {selectedItem && (
        <DetailPanel item={selectedItem} onClose={() => setSelectedItem(null)} />
      )}
    </div>
  );
}
