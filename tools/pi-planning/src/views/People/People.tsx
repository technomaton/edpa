import { useMemo } from 'react';
import { useConfigStore } from '../../store/config-store';
import { useBacklogStore } from '../../store/backlog-store';

const DONE_STATUSES = new Set(['done', 'closed', 'accepted', 'complete', 'completed']);

// ─── Velocity Sparkline ───────────────────────────────────────────────────────

function VelocitySparkline({ values, width = 80, height = 22 }: {
  values: number[];
  width?: number;
  height?: number;
}) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const step = width / (values.length - 1);
  const pts = values.map((v, i) => {
    const x = Math.round(i * step);
    const y = Math.round(height - (v / max) * (height - 4) - 2);
    return `${x},${y}`;
  }).join(' ');
  const last = values[values.length - 1];
  const trend = values.length >= 2 ? last - values[values.length - 2] : 0;
  const color = trend > 0 ? '#059669' : trend < 0 ? '#dc2626' : '#8892a8';

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5}
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={parseFloat(pts.split(' ').pop()!.split(',')[0])}
        cy={parseFloat(pts.split(' ').pop()!.split(',')[1])}
        r={2.5} fill={color} />
    </svg>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function People() {
  const people = useConfigStore(s => s.people);
  const teams = useConfigStore(s => s.teams);
  const pi = useConfigStore(s => s.currentPI());
  const items = useBacklogStore(s => s.items);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);

  const activeIteration = pi?.iterations.find(i => i.status === 'active')?.id;

  // Load (total JS) per person in the active iteration
  const loadPerPerson = useMemo(() => {
    const map: Record<string, number> = {};
    if (!activeIteration) return map;
    items
      .filter(i => i.type === 'Story' && i.iteration?.startsWith(activeIteration))
      .forEach(i => {
        const key = i.assignee || '';
        map[key] = (map[key] || 0) + (i.js || 0);
      });
    return map;
  }, [items, activeIteration]);

  // Velocity: done stories JS per person per iteration (sparkline data)
  const velocityPerPerson = useMemo(() => {
    const iterations = pi?.iterations ?? [];
    if (iterations.length === 0) return {} as Record<string, number[]>;
    const map: Record<string, number[]> = {};
    for (const p of people) map[p.id] = iterations.map(() => 0);
    for (const item of items) {
      if (item.type !== 'Story') continue;
      if (!DONE_STATUSES.has((item.status || '').toLowerCase())) continue;
      const pid = item.assignee || '';
      if (!map[pid]) continue;
      const idx = iterations.findIndex(it => it.id === item.iteration);
      if (idx >= 0) map[pid][idx] += item.js || 0;
    }
    return map;
  }, [items, people, pi]);

  return (
    <div className="people-view">
      <div className="people-header">
        <h2 className="people-header__title">Team Roster</h2>
        {activeIteration && (
          <span className="people-header__iter">Load for {activeIteration}</span>
        )}
      </div>

      {teamIds.map(teamId => {
        const teamPeople = people.filter(p => p.team === teamId);
        const teamConfig = teams.find(t => t.id === teamId);
        const totalCapacity = teamPeople.reduce((s, p) => s + p.capacity, 0);
        const totalFte = teamPeople.reduce((s, p) => s + p.fte, 0);

        return (
          <div key={teamId} className="people-team">
            <div className="people-team__header">
              <span className="people-team__name">{teamId}</span>
              <span className="people-team__stats">
                {teamPeople.length} members &middot; {totalFte.toFixed(1)} FTE &middot;
                {totalCapacity}h capacity
                {teamConfig && ` · PF ${teamConfig.planning_factor}`}
              </span>
            </div>
            <div className="people-grid">
              {teamPeople.map(person => {
                const load = loadPerPerson[person.id] || 0;
                const pct = person.capacity > 0 ? (load / person.capacity) * 100 : 0;
                const sparkData = velocityPerPerson[person.id] ?? [];
                const totalDone = sparkData.reduce((s, v) => s + v, 0);
                return (
                  <div key={person.id} className="person-card">
                    <div className="person-card__avatar">
                      {person.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
                    </div>
                    <div className="person-card__info">
                      <span className="person-card__name">{person.name}</span>
                      <span className="person-card__role">{person.role}</span>
                    </div>
                    <div className="person-card__stats">
                      <span className="person-card__fte">{person.fte} FTE</span>
                      <span className="person-card__cap">{person.capacity}h</span>
                    </div>
                    <div className="person-card__bar">
                      <div className="capacity-bar">
                        <div
                          className={'capacity-bar__fill' + (pct > 100 ? ' capacity-bar__fill--over' : '')}
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                      <span className={'capacity-label' + (pct > 100 ? ' capacity-label--over' : '')}>
                        {load}/{person.capacity}
                      </span>
                    </div>
                    {sparkData.some(v => v > 0) && (
                      <div className="person-card__spark">
                        <VelocitySparkline values={sparkData} />
                        <span className="person-card__spark-label">
                          {totalDone} JS done
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
