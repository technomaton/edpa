import { Fragment, useMemo, useState, type DragEvent } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, Person, Iteration } from '../../types/edpa';

// -- Story Card ---------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  Story: '#ea580c',
  Feature: '#0891b2',
  Defect: '#dc2626',
};

function StoryCard({ item, onDragStart }: { item: WorkItem; onDragStart: (e: DragEvent) => void }) {
  const isDone = item.status === 'Done';
  const color = TYPE_COLORS[item.type] || '#8892a8';

  return (
    <div
      className="tb-card"
      draggable
      onDragStart={onDragStart}
      style={{ borderLeftColor: color, opacity: isDone ? 0.5 : 1 }}
    >
      <div className="tb-card__head">
        <span className="tb-card__id" style={{ color }}>{item.id}</span>
        {item.js != null && <span className="tb-card__js">JS {item.js}</span>}
      </div>
      <div className="tb-card__title">{item.title}</div>
      <div className="tb-card__foot">
        <span className="tb-card__assignee">{item.assignee || '-'}</span>
        <span className="tb-card__status">{item.status}</span>
      </div>
    </div>
  );
}

// -- Table Row ----------------------------------------------------------------

function TableRow({ item }: { item: WorkItem }) {
  const isDone = item.status === 'Done';
  return (
    <tr className={`tb-table__row ${isDone ? 'tb-table__row--done' : ''}`}>
      <td className="tb-table__td tb-table__td--id">{item.id}</td>
      <td className="tb-table__td">{item.title}</td>
      <td className="tb-table__td tb-table__td--num">{item.js ?? '-'}</td>
      <td className="tb-table__td">{item.assignee || '-'}</td>
      <td className="tb-table__td">{item.status}</td>
      <td className="tb-table__td">{item.parent || '-'}</td>
    </tr>
  );
}

// -- Cell (person × iteration) ------------------------------------------------

function TeamCell({
  personId,
  iterationId,
  items,
  capacity,
  viewMode,
  onDrop,
}: {
  personId: string;
  iterationId: string;
  items: WorkItem[];
  capacity: { used: number; available: number };
  viewMode: 'cards' | 'table';
  onDrop: (itemId: string, assignee: string, iteration: string) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const pct = capacity.available > 0 ? Math.min(100, (capacity.used / capacity.available) * 100) : 0;
  const over = capacity.used > capacity.available && capacity.available > 0;

  const handleDragStart = (item: WorkItem) => (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className={`tb-cell ${dragOver ? 'tb-cell--drag-over' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault();
        setDragOver(false);
        const id = e.dataTransfer.getData('text/plain');
        if (id) onDrop(id, personId, iterationId);
      }}
    >
      {viewMode === 'cards' ? (
        <div className="tb-cell__cards">
          {items.map(item => (
            <StoryCard key={item.id} item={item} onDragStart={handleDragStart(item)} />
          ))}
        </div>
      ) : (
        items.length > 0 ? (
          <table className="tb-table">
            <tbody>
              {items.map(item => <TableRow key={item.id} item={item} />)}
            </tbody>
          </table>
        ) : null
      )}
      {capacity.available > 0 && (
        <div className="tb-cell__cap">
          <div className="capacity-bar">
            <div
              className={`capacity-bar__fill ${over ? 'capacity-bar__fill--over' : ''}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className={`capacity-label ${over ? 'capacity-label--over' : ''}`}>
            {capacity.used}/{capacity.available}
          </span>
        </div>
      )}
    </div>
  );
}

// -- Main Component -----------------------------------------------------------

export function TeamBoard() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const people = useConfigStore(s => s.people);
  const pi = useConfigStore(s => s.currentPI());
  const isReadonly = useConfigStore(s => s.isReadonly);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const [selectedTeam, setSelectedTeam] = useState(teamIds[0] || '');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  const iterations = pi?.iterations || [];
  const teamPeople = useMemo(
    () => people.filter(p => p.team === selectedTeam),
    [people, selectedTeam],
  );

  // All stories for this PI
  const iterationIds = useMemo(() => new Set(iterations.map(it => it.id)), [iterations]);
  const stories = useMemo(
    () => items.filter(i =>
      (i.type === 'Story' || i.type === 'Feature') &&
      (i.iteration ? iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id)) : false),
    ),
    [items, iterationIds, iterations],
  );

  // Unassigned stories (in PI but no assignee or assignee not in team)
  const unassignedStories = useMemo(
    () => stories.filter(s =>
      !s.assignee || !teamPeople.some(p => p.id === s.assignee),
    ),
    [stories, teamPeople],
  );

  const handleDrop = (itemId: string, assignee: string, iteration: string) => {
    if (isReadonly) return;
    updateItem(itemId, { assignee: assignee || undefined, iteration });
    saveItem(itemId);
  };

  const gridCols = iterations.length;

  return (
    <div className="tb-container">
      {/* Header */}
      <div className="tb-header">
        <h2 className="tb-header__title">Team Board</h2>
        <div className="tb-header__controls">
          <select
            value={selectedTeam}
            onChange={e => setSelectedTeam(e.target.value)}
            className="tb-select"
          >
            {teamIds.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <div className="tb-view-toggle">
            <button
              className={`tb-view-btn ${viewMode === 'cards' ? 'tb-view-btn--active' : ''}`}
              onClick={() => setViewMode('cards')}
              title="Card view"
            >
              ▦
            </button>
            <button
              className={`tb-view-btn ${viewMode === 'table' ? 'tb-view-btn--active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Table view"
            >
              ≡
            </button>
          </div>
        </div>
      </div>

      {/* Grid: persons × iterations */}
      <div className="tb-grid" style={{ gridTemplateColumns: `140px repeat(${gridCols}, 1fr)` }}>
        {/* Corner */}
        <div className="tb-corner">
          <span className="tb-corner__label">Person / Iteration</span>
        </div>

        {/* Iteration headers */}
        {iterations.map(iter => (
          <div key={iter.id} className={`tb-col-header ${iter.status === 'active' ? 'tb-col-header--active' : ''}`}>
            <span className="tb-col-header__id">{iter.id}</span>
            <span className="tb-col-header__dates">{iter.dates}</span>
            <span className={`tb-col-header__status tb-col-header__status--${iter.status}`}>
              {iter.status}
            </span>
          </div>
        ))}

        {/* Person rows */}
        {teamPeople.map(person => (
          <Fragment key={person.id}>
            <div className="tb-row-header">
              <span className="tb-row-header__name">{person.name}</span>
              <span className="tb-row-header__role">{person.role}</span>
              <span className="tb-row-header__cap">{person.capacity}h</span>
            </div>
            {iterations.map(iter => {
              const cellStories = stories.filter(
                s => s.assignee === person.id && s.iteration?.startsWith(iter.id),
              );
              const used = cellStories.reduce((sum, s) => sum + (s.js || 0), 0);
              return (
                <TeamCell
                  key={`${person.id}-${iter.id}`}
                  personId={person.id}
                  iterationId={iter.id}
                  items={cellStories}
                  capacity={{ used, available: person.capacity }}
                  viewMode={viewMode}
                  onDrop={handleDrop}
                />
              );
            })}
          </Fragment>
        ))}

        {/* Unassigned row */}
        {unassignedStories.length > 0 && (
          <>
            <div className="tb-row-header tb-row-header--unassigned">
              <span className="tb-row-header__name">Unassigned</span>
              <span className="tb-row-header__role">{unassignedStories.length} items</span>
            </div>
            {iterations.map(iter => {
              const cellStories = unassignedStories.filter(
                s => s.iteration?.startsWith(iter.id),
              );
              return (
                <TeamCell
                  key={`unassigned-${iter.id}`}
                  personId=""
                  iterationId={iter.id}
                  items={cellStories}
                  capacity={{ used: 0, available: 0 }}
                  viewMode={viewMode}
                  onDrop={handleDrop}
                />
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
