import { useMemo, useState, type DragEvent } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, Person } from '../../types/edpa';

const STATUS_COLORS: Record<string, string> = {
  Done: '#059669',
  'In Progress': '#6366f1',
  Active: '#6366f1',
  Planned: '#8892a8',
};

function StoryCard({ item }: { item: WorkItem }) {
  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const isDone = item.status === 'Done';
  return (
    <div
      className="story-card"
      draggable
      onDragStart={onDragStart}
      style={{ opacity: isDone ? 0.5 : 1 }}
    >
      <div className="story-card__head">
        <span className="story-card__id">{item.id}</span>
        <span className="story-card__js">{item.js}</span>
      </div>
      <div className="story-card__title">{item.title}</div>
      <div className="story-card__foot">
        <span className="story-card__assignee">{item.assignee || '-'}</span>
        <span
          className="story-card__status"
          style={{ color: STATUS_COLORS[item.status] || '#8892a8' }}
        >
          {item.status}
        </span>
      </div>
    </div>
  );
}

function PersonLane({
  person,
  stories,
  iterationId,
  onDrop,
}: {
  person: Person;
  stories: WorkItem[];
  iterationId: string;
  onDrop: (itemId: string, assignee: string, iteration: string) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const totalJs = stories.reduce((s, i) => s + (i.js || 0), 0);
  const pct = person.capacity > 0 ? (totalJs / person.capacity) * 100 : 0;

  return (
    <div
      className={`person-lane ${dragOver ? 'person-lane--drag-over' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault();
        setDragOver(false);
        const id = e.dataTransfer.getData('text/plain');
        if (id) onDrop(id, person.id, iterationId);
      }}
    >
      <div className="person-lane__header">
        <span className="person-lane__name">{person.name}</span>
        <span className="person-lane__role">{person.role}</span>
        <div className="person-lane__load">
          <div className="capacity-bar" style={{ width: 60 }}>
            <div
              className={`capacity-bar__fill ${pct > 100 ? 'capacity-bar__fill--over' : ''}`}
              style={{ width: `${Math.min(100, pct)}%` }}
            />
          </div>
          <span className={`capacity-label ${pct > 100 ? 'capacity-label--over' : ''}`}>
            {totalJs}/{person.capacity}
          </span>
        </div>
      </div>
      <div className="person-lane__cards">
        {stories.map(s => <StoryCard key={s.id} item={s} />)}
      </div>
    </div>
  );
}

export function TeamBoard() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const people = useConfigStore(s => s.people);
  const pi = useConfigStore(s => s.pi);
  const teams = useConfigStore(s => s.teams);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const [selectedTeam, setSelectedTeam] = useState(teamIds[0] || '');
  const [selectedIteration, setSelectedIteration] = useState(
    pi?.iterations.find(i => i.status === 'active')?.id || pi?.iterations[0]?.id || '',
  );

  const teamPeople = useMemo(
    () => people.filter(p => p.team === selectedTeam),
    [people, selectedTeam],
  );

  const stories = useMemo(
    () => items.filter(i =>
      i.type === 'Story' &&
      i.iteration?.startsWith(selectedIteration),
    ),
    [items, selectedIteration],
  );

  const handleDrop = (itemId: string, assignee: string, iteration: string) => {
    updateItem(itemId, { assignee, iteration });
    saveItem(itemId);
  };

  return (
    <div className="team-board">
      <div className="team-board__header">
        <h2 className="team-board__title">Team Board</h2>
        <div className="team-board__filters">
          <select
            value={selectedTeam}
            onChange={e => setSelectedTeam(e.target.value)}
            className="tb-select"
          >
            {teamIds.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select
            value={selectedIteration}
            onChange={e => setSelectedIteration(e.target.value)}
            className="tb-select"
          >
            {pi?.iterations.map(it => (
              <option key={it.id} value={it.id}>
                {it.id} {it.status === 'active' ? '(active)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="team-board__lanes">
        {teamPeople.map(person => (
          <PersonLane
            key={person.id}
            person={person}
            stories={stories.filter(s => s.assignee === person.id)}
            iterationId={selectedIteration}
            onDrop={handleDrop}
          />
        ))}
        {/* Unassigned lane */}
        <PersonLane
          person={{ id: '', name: 'Unassigned', role: '-', team: selectedTeam, fte: 0, capacity: 0 }}
          stories={stories.filter(s => !s.assignee || !teamPeople.some(p => p.id === s.assignee))}
          iterationId={selectedIteration}
          onDrop={handleDrop}
        />
      </div>
    </div>
  );
}
