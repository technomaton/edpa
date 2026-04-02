import { useMemo } from 'react';
import type { WorkItem, Person, Team, Iteration, PIConfig, PIEvent } from '../../../types/edpa';

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
  Feature:    { border: '#0891b2', bg: 'rgba(8,145,178,0.06)' },
  Story:      { border: '#ea580c', bg: 'rgba(234,88,12,0.06)' },
  Milestone:  { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)' },
  Event:      { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)' },
};

function getTeamForItem(item: WorkItem, personTeam: Record<string, string>): string {
  return personTeam[item.owner || ''] || personTeam[item.assignee || ''] || 'Unassigned';
}

export function ProgramBoardSection({ items: rawItems, pi: rawPi, people: rawPeople, teams: rawTeams, width, height }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;
  const people = rawPeople as Person[];
  const teams = rawTeams as Team[];
  const iterations = pi?.iterations || [];

  const personTeam = useMemo(() => {
    const m: Record<string, string> = {};
    people.forEach(p => { m[p.id] = p.team; });
    return m;
  }, [people]);

  const sharedServiceIds = new Set(pi?.shared_services || []);
  const allTeamIds = [...new Set(people.map(p => p.team))];
  const internalTeams = allTeamIds.filter(t => !sharedServiceIds.has(t) && !teams.find(tm => tm.id === t && tm.type === 'external'));
  const externalTeams = allTeamIds.filter(t => sharedServiceIds.has(t) || !!teams.find(tm => tm.id === t && tm.type === 'external'));
  const allRows = ['Milestones', ...internalTeams, ...externalTeams];

  const iterationIds = new Set(iterations.map(it => it.id));
  const boardItems = items.filter(i =>
    (i.type === 'Feature' || i.type === 'Story' || i.type === 'Milestone' || i.type === 'Event') &&
    (i.iteration ? iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id)) : true)
  );

  // Synthetic events from PI config
  const piEvents: WorkItem[] = (pi?.events || [])
    .filter((evt: PIEvent) => evt.iteration && iterationIds.has(evt.iteration))
    .map((evt: PIEvent, i: number) => ({
      id: `EVT-${i + 1}`, type: 'Event' as const, title: evt.title,
      js: 0, status: 'Planned' as const, parent: null,
      iteration: evt.iteration, contributors: [],
    }));

  // Group items by cell
  const cellItems = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    [...boardItems, ...piEvents].forEach(item => {
      const isMilestone = item.type === 'Milestone' || item.type === 'Event';
      const row = isMilestone ? 'Milestones' : getTeamForItem(item, personTeam);
      const iter = iterations.find(it => item.iteration?.startsWith(it.id));
      if (iter) {
        const key = `${row}::${iter.id}`;
        if (!map[key]) map[key] = [];
        map[key].push(item);
      }
    });
    return map;
  }, [boardItems, piEvents, iterations, personTeam]);

  const colW = iterations.length > 0 ? Math.floor((width - 140) / iterations.length) : 200;
  const rowH = 120;

  return (
    <div className="pb-section" style={{ width }}>
      <table className="pb-section__table">
        <thead>
          <tr>
            <th className="pb-section__corner" style={{ width: 130 }}>Team / Iter</th>
            {iterations.map(iter => (
              <th key={iter.id} className={`pb-section__col-header ${iter.status === 'active' ? 'pb-section__col-header--active' : ''}`}
                style={{ width: colW }}>
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
          {allRows.map((row, ri) => {
            const isExternal = externalTeams.includes(row);
            const isMilestones = row === 'Milestones';
            return (
              <tr key={row} className={isMilestones ? 'pb-section__row--milestones' : isExternal ? 'pb-section__row--external' : ''}>
                <td className="pb-section__row-header">
                  <span className="pb-section__row-name">{row}</span>
                </td>
                {iterations.map(iter => {
                  const items = cellItems[`${row}::${iter.id}`] || [];
                  return (
                    <td key={iter.id} className={`pb-section__cell ${iter.type === 'IP' ? 'pb-section__cell--ip' : ''}`}>
                      {items.map(item => {
                        const colors = TYPE_COLORS[item.type] || TYPE_COLORS.Feature;
                        return (
                          <div key={item.id} className="pb-section__card"
                            style={{ borderLeftColor: colors.border, background: colors.bg }}>
                            <span className="pb-section__card-id" style={{ color: colors.border }}>{item.id}</span>
                            <span className="pb-section__card-title">{item.title}</span>
                          </div>
                        );
                      })}
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
