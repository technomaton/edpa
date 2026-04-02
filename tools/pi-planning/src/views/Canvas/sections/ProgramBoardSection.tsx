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

// SAFe color coding:
// Red = has incoming dependency (significant dependency)
// Blue = independent / final delivery (no incoming deps)
// Yellow/Orange = milestone or event
const DEP_STYLES: Record<string, { border: string; bg: string; idColor: string }> = {
  dependent:   { border: '#dc2626', bg: 'rgba(220,38,38,0.06)',  idColor: '#dc2626' },
  independent: { border: '#2563eb', bg: 'rgba(37,99,235,0.06)',  idColor: '#2563eb' },
  milestone:   { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)', idColor: '#d97706' },
};

function getTeamForItem(item: WorkItem, personTeam: Record<string, string>): string {
  return personTeam[item.owner || ''] || personTeam[item.assignee || ''] || 'Unassigned';
}

type DepCategory = 'dependent' | 'independent' | 'milestone';

function PBCard({ item, isReadonly, depCategory }: { item: WorkItem; isReadonly: boolean; depCategory: DepCategory }) {
  const style = DEP_STYLES[depCategory];
  const isDone = item.status === 'Done';

  const onDragStart = (e: DragEvent) => {
    if (isReadonly) return;
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className={`pb-section__card pb-section__card--${depCategory} ${isDone ? 'pb-section__card--done' : ''}`}
      style={{ borderLeftColor: style.border, background: style.bg }}
      draggable={!isReadonly}
      onDragStart={onDragStart}
      data-item-id={item.id}
    >
      <div className="pb-section__card-head">
        <span className="pb-section__card-id" style={{ color: style.idColor }}>{item.id}</span>
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

  // Dependency analysis — classify each item
  const depCategories = useMemo(() => {
    const hasIncoming = new Set<string>();
    boardItems.forEach(item => {
      if (item.depends_on) {
        item.depends_on.forEach(() => hasIncoming.add(item.id));
      }
    });
    const map: Record<string, DepCategory> = {};
    boardItems.forEach(item => {
      if (item.type === 'Milestone' || item.type === 'Event') {
        map[item.id] = 'milestone';
      } else if (hasIncoming.has(item.id)) {
        map[item.id] = 'dependent';
      } else {
        map[item.id] = 'independent';
      }
    });
    return map;
  }, [boardItems]);

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

                  const isSingleWeek = (pi?.iteration_weeks || 2) <= 1;
                  const w1Items = cellCardItems.filter(i => !i.iteration_half || i.iteration_half === 1);
                  const w2Items = cellCardItems.filter(i => i.iteration_half === 2);

                  const handleHalfDrop = (e: DragEvent, half: 1 | 2) => {
                    e.preventDefault();
                    setDropTarget(null);
                    if (isReadonly) return;
                    const itemId = e.dataTransfer.getData('text/plain');
                    if (!itemId) return;
                    const item = items.find(i => i.id === itemId);
                    if (!item) return;
                    if (iter.type === 'IP' && item.type !== 'Milestone' && item.type !== 'Event') return;
                    const changes: Partial<WorkItem> = { iteration: iter.id };
                    if (!isSingleWeek) changes.iteration_half = half;
                    if (item.iteration !== iter.id || item.iteration_half !== half) {
                      updateItem(itemId, changes);
                      saveItem(itemId);
                    }
                  };

                  return (
                    <td key={iter.id}
                      className={`pb-section__cell ${isIP ? 'pb-section__cell--ip' : ''}`}
                    >
                      {isSingleWeek ? (
                        /* Single week — one drop zone */
                        <div
                          className={`pb-section__half ${dropTarget === `${cellKey}::W1` ? 'pb-section__half--drop' : ''}`}
                          onDragOver={e => { e.preventDefault(); setDropTarget(`${cellKey}::W1`); }}
                          onDragLeave={() => setDropTarget(null)}
                          onDrop={e => handleHalfDrop(e, 1)}
                        >
                          <span className="pb-section__half-label">W1</span>
                          {w1Items.map(item => (
                            <PBCard key={item.id} item={item} isReadonly={isReadonly} depCategory={depCategories[item.id] || 'independent'} />
                          ))}
                        </div>
                      ) : (
                        /* Two halves — W1 | W2 */
                        <div className="pb-section__halves">
                          <div
                            className={`pb-section__half ${dropTarget === `${cellKey}::W1` ? 'pb-section__half--drop' : ''}`}
                            onDragOver={e => { e.preventDefault(); setDropTarget(`${cellKey}::W1`); }}
                            onDragLeave={() => setDropTarget(null)}
                            onDrop={e => handleHalfDrop(e, 1)}
                          >
                            <span className="pb-section__half-label">W1</span>
                            {w1Items.map(item => (
                              <PBCard key={item.id} item={item} isReadonly={isReadonly} depCategory={depCategories[item.id] || 'independent'} />
                            ))}
                          </div>
                          <div className="pb-section__divider" />
                          <div
                            className={`pb-section__half ${dropTarget === `${cellKey}::W2` ? 'pb-section__half--drop' : ''}`}
                            onDragOver={e => { e.preventDefault(); setDropTarget(`${cellKey}::W2`); }}
                            onDragLeave={() => setDropTarget(null)}
                            onDrop={e => handleHalfDrop(e, 2)}
                          >
                            <span className="pb-section__half-label">W2</span>
                            {w2Items.map(item => (
                              <PBCard key={item.id} item={item} isReadonly={isReadonly} depCategory={depCategories[item.id] || 'independent'} />
                            ))}
                          </div>
                        </div>
                      )}
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
