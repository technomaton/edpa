import { useMemo } from 'react';
import { useConfigStore } from '../../store/config-store';
import { useBacklogStore } from '../../store/backlog-store';

export function People() {
  const people = useConfigStore(s => s.people);
  const teams = useConfigStore(s => s.teams);
  const pi = useConfigStore(s => s.currentPI());
  const items = useBacklogStore(s => s.items);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);

  // Compute load per person for active iteration
  const activeIteration = pi?.iterations.find(i => i.status === 'active')?.id;
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
                {teamConfig && ` &middot; PF ${teamConfig.planning_factor}`}
              </span>
            </div>
            <div className="people-grid">
              {teamPeople.map(person => {
                const load = loadPerPerson[person.id] || 0;
                const pct = person.capacity > 0 ? (load / person.capacity) * 100 : 0;
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
                          className={`capacity-bar__fill ${pct > 100 ? 'capacity-bar__fill--over' : ''}`}
                          style={{ width: `${Math.min(100, pct)}%` }}
                        />
                      </div>
                      <span className={`capacity-label ${pct > 100 ? 'capacity-label--over' : ''}`}>
                        {load}/{person.capacity}
                      </span>
                    </div>
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
