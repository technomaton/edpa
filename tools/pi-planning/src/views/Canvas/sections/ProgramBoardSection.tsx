import { useMemo, useState, Fragment, type DragEvent } from 'react';
import type { WorkItem, Person, Team, PIConfig, PIEvent } from '../../../types/edpa';
import { useBacklogStore } from '../../../store/backlog-store';

interface Props {
  items: unknown[];
  pi: unknown;
  people: unknown[];
  teams: unknown[];
  isReadonly: boolean;
  width: number;
  height: number;
}

const TYPE_COLORS: Record<string, { border: string; bg: string }> = {
  Feature:   { border: '#0891b2', bg: 'rgba(8,145,178,0.06)' },
  Story:     { border: '#ea580c', bg: 'rgba(234,88,12,0.06)' },
  Milestone: { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)' },
  Event:     { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)' },
};

function getTeamForItem(item: WorkItem, personTeam: Record<string, string>): string {
  return personTeam[item.owner || ''] || personTeam[item.assignee || ''] || 'Unassigned';
}

function PBCard({ item, isReadonly }: { item: WorkItem; isReadonly: boolean }) {
  const colors = TYPE_COLORS[item.type] || TYPE_COLORS.Feature;
  const isDone = item.status === 'Done';
  const hasDeps = item.depends_on && item.depends_on.length > 0;

  const onDragStart = (e: DragEvent) => {
    if (isReadonly) return;
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className={`pb-section__card ${isDone ? 'pb-section__card--done' : ''} ${hasDeps ? 'pb-section__card--dep' : ''}`}
      style={{ borderLeftColor: colors.border, background: colors.bg }}
      draggable={!isReadonly}
      onDragStart={onDragStart}
    >
      <div className="pb-section__card-head">
        <span className="pb-section__card-id" style={{ color: colors.border }}>{item.id}</span>
        {item.js != null && item.js > 0 && <span className="pb-section__card-js">JS {item.js}</span>}
        {item.wsjf != null && <span className="pb-section__card-wsjf">W {item.wsjf.toFixed(1)}</span>}
      </div>
      <span className="pb-section__card-title">{item.title}</span>
      <div className="pb-section__card-foot">
        <span className="pb-section__card-owner">{item.owner || item.assignee || ''}</span>
        <span className="pb-section__card-status">{item.status}</span>
      </div>
    </div>
  );
}

export function ProgramBoardSection({ items: rawItems, pi: rawPi, people: rawPeople, teams: rawTeams, isReadonly, width }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;
  const people = rawPeople as Person[];
  const allTeams = rawTeams as Team[];
  const iterations = pi?.iterations || [];
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);

  const personTeam = useMemo(() => {
    const m: Record<string, string> = {};
    people.forEach(p => { m[p.id] = p.team; });
    return m;
  }, [people]);

  const sharedServiceIds = new Set(pi?.shared_services || []);
  const allTeamIds = [...new Set(people.map(p => p.team))];
  const internalTeams = allTeamIds.filter(t => !sharedServiceIds.has(t) && !allTeams.find(tm => tm.id === t && tm.type === 'external'));
  const externalTeams = allTeamIds.filter(t => sharedServiceIds.has(t) || !!allTeams.find(tm => tm.id === t && tm.type === 'external'));
  const allRows = ['Milestones', ...internalTeams, ...externalTeams];

  const iterationIds = new Set(iterations.map(it => it.id));

  // All board items + synthetic events
  const boardItems = useMemo(() => {
    const filtered = items.filter(i =>
      (i.type === 'Feature' || i.type === 'Story' || i.type === 'Milestone' || i.type === 'Event') &&
      (i.iteration ? iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id)) : true)
    );
    const syntheticEvents: WorkItem[] = (pi?.events || [])
      .filter((evt: PIEvent) => evt.iteration && iterationIds.has(evt.iteration))
      .map((evt: PIEvent, i: number) => ({
        id: `EVT-${i + 1}`, type: 'Event' as const, title: evt.title,
        js: 0, status: 'Planned' as const, parent: null,
        iteration: evt.iteration, contributors: [],
      }));
    return [...filtered, ...syntheticEvents];
  }, [items, iterations, iterationIds, pi?.events]);

  // Group by cell
  const cellItems = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    boardItems.forEach(item => {
      const isMilestone = item.type === 'Milestone' || item.type === 'Event';
      const row = isMilestone ? 'Milestones' : getTeamForItem(item, personTeam);
      const iter = iterations.find(it => item.iteration?.startsWith(it.id));
      if (iter) {
        const key = `${row}::${iter.id}`;
        if (!map[key]) map[key] = [];
        map[key].push(item);
      }
    });
    // Sort by WSJF
    Object.values(map).forEach(arr => arr.sort((a, b) => (b.wsjf || 0) - (a.wsjf || 0)));
    return map;
  }, [boardItems, iterations, personTeam]);

  // Capacity per cell
  const planningFactors = useMemo(() => {
    const m: Record<string, number> = {};
    allTeams.forEach(t => { m[t.id] = t.planning_factor; });
    return m;
  }, [allTeams]);

  // Drop handler
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const handleDrop = (e: DragEvent, iterationId: string) => {
    e.preventDefault();
    setDropTarget(null);
    if (isReadonly) return;
    const itemId = e.dataTransfer.getData('text/plain');
    if (!itemId) return;
    const item = items.find(i => i.id === itemId);
    if (!item) return;
    // Block IP iterations
    const iter = iterations.find(it => it.id === iterationId);
    if (iter?.type === 'IP' && item.type !== 'Milestone' && item.type !== 'Event') return;
    if (item.iteration !== iterationId) {
      updateItem(itemId, { iteration: iterationId });
      saveItem(itemId);
    }
  };

  return (
    <div className="pb-section" style={{ width }}>
      <table className="pb-section__table">
        <thead>
          <tr>
            <th className="pb-section__corner" style={{ width: 130 }}>Team / Iter</th>
            {iterations.map(iter => (
              <th key={iter.id}
                className={`pb-section__col-header ${iter.status === 'active' ? 'pb-section__col-header--active' : ''}`}>
                <div className="pb-section__iter-id">
                  {iter.type ? `${iter.id} (${iter.type})` : iter.id}
                </div>
                <div className="pb-section__iter-dates">{iter.dates}</div>
                <div className={`pb-section__iter-status pb-section__iter-status--${iter.status}`}>{iter.status}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allRows.map(row => {
            const isExternal = externalTeams.includes(row);
            const isMilestones = row === 'Milestones';
            const teamPeople = isMilestones ? [] : people.filter(p => p.team === row);
            return (
              <tr key={row} className={isMilestones ? 'pb-section__row--milestones' : isExternal ? 'pb-section__row--external' : ''}>
                <td className="pb-section__row-header">
                  <span className="pb-section__row-name">{row}</span>
                  {!isMilestones && (
                    <span className="pb-section__row-count">{teamPeople.length} members</span>
                  )}
                </td>
                {iterations.map(iter => {
                  const cellKey = `${row}::${iter.id}`;
                  const cellCardItems = cellItems[cellKey] || [];
                  const isIP = iter.type === 'IP';
                  const isDrop = dropTarget === cellKey;
                  // Capacity
                  const available = isMilestones ? 0 :
                    teamPeople.reduce((s, p) => s + p.capacity, 0) * (planningFactors[row] || 0.8);
                  const used = cellCardItems.reduce((s, i) => s + (i.js || 0), 0);

                  return (
                    <td key={iter.id}
                      className={`pb-section__cell ${isIP ? 'pb-section__cell--ip' : ''} ${isDrop ? 'pb-section__cell--drop' : ''}`}
                      onDragOver={e => { e.preventDefault(); setDropTarget(cellKey); }}
                      onDragLeave={() => setDropTarget(null)}
                      onDrop={e => handleDrop(e, iter.id)}
                    >
                      {cellCardItems.map(item => (
                        <PBCard key={item.id} item={item} isReadonly={isReadonly} />
                      ))}
                      {available > 0 && (
                        <div className="pb-section__cap">
                          <div className="pb-section__cap-bar">
                            <div className={`pb-section__cap-fill ${used > available ? 'pb-section__cap-fill--over' : ''}`}
                              style={{ width: `${Math.min(100, (used / available) * 100)}%` }} />
                          </div>
                          <span className={`pb-section__cap-label ${used > available ? 'pb-section__cap-label--over' : ''}`}>
                            {used}/{available}
                          </span>
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
