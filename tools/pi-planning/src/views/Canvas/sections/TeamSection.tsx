import { useMemo, useState, useEffect, useCallback } from 'react';
import type { WorkItem, Person, Team, PIConfig } from '../../../types/edpa';
import { api } from '../../../lib/api';
import type { ObjectivesData, PIObjective } from '../../../types/edpa';

interface Props {
  teamId: string;
  items: unknown[];
  pi: unknown;
  people: unknown[];
  teams: unknown[];
  selectedPI: string | null;
  isReadonly: boolean;
  width: number;
  height: number;
}

const STATUS_COLORS: Record<string, string> = {
  Done: '#059669', 'In Progress': '#6366f1', Active: '#6366f1', Planned: '#8892a8',
};

export function TeamSection({ teamId, items: rawItems, pi: rawPi, people: rawPeople, selectedPI, isReadonly, width, height }: Props) {
  const items = rawItems as WorkItem[];
  const pi = rawPi as PIConfig | undefined;
  const people = rawPeople as Person[];
  const iterations = pi?.iterations || [];

  const teamPeople = useMemo(() => people.filter(p => p.team === teamId), [people, teamId]);
  const totalCapacity = teamPeople.reduce((s, p) => s + p.capacity, 0);

  // Filter stories for this team
  const iterationIds = useMemo(() => new Set(iterations.map(it => it.id)), [iterations]);
  const teamStories = useMemo(() => {
    const teamPersonIds = new Set(teamPeople.map(p => p.id));
    return items.filter(i => {
      if (i.type !== 'Story' && i.type !== 'Feature') return false;
      const owner = i.owner || i.assignee || '';
      if (!teamPersonIds.has(owner)) return false;
      if (!i.iteration) return true;
      return iterationIds.has(i.iteration) || iterations.some(it => i.iteration!.startsWith(it.id));
    });
  }, [items, teamPeople, iterationIds, iterations]);

  // Risks for this team
  const teamRisks = useMemo(() =>
    items.filter(i => i.type === 'Risk' && i.iteration?.startsWith(selectedPI || '')),
    [items, selectedPI],
  );

  // Objectives
  const [objectives, setObjectives] = useState<ObjectivesData | null>(null);
  const [confidence, setConfidence] = useState(0);

  useEffect(() => {
    if (!selectedPI) return;
    api.getObjectives(selectedPI).then(data => {
      setObjectives(data);
      const teamData = data?.teams?.[teamId];
      setConfidence(teamData?.confidence || 0);
    }).catch(() => {});
  }, [selectedPI, teamId]);

  const teamObjectives = objectives?.teams?.[teamId];
  const committed = teamObjectives?.committed || [];
  const stretch = teamObjectives?.stretch || [];
  const totalBV = committed.reduce((s: number, o: PIObjective) => s + (o.bv || 0), 0)
    + stretch.reduce((s: number, o: PIObjective) => s + (o.bv || 0), 0);

  // Group stories by iteration
  const storiesByIter = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    teamStories.forEach(s => {
      const iter = iterations.find(it => s.iteration?.startsWith(it.id));
      if (iter) {
        if (!map[iter.id]) map[iter.id] = [];
        map[iter.id].push(s);
      }
    });
    return map;
  }, [teamStories, iterations]);

  return (
    <div className="team-section" style={{ width }}>
      {/* Top row: Members + Objectives */}
      <div className="team-section__top">
        {/* Members */}
        <div className="team-section__members">
          <div className="team-section__subtitle">Team Members</div>
          <table className="team-section__members-table">
            <thead>
              <tr>
                <th>Name</th><th>Role</th><th>FTE</th><th>Cap</th>
              </tr>
            </thead>
            <tbody>
              {teamPeople.map(p => (
                <tr key={p.id}>
                  <td>{p.name}</td><td>{p.role}</td><td>{p.fte}</td><td>{p.capacity}h</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="team-section__cap-total">
            Total: {teamPeople.length} members, {totalCapacity}h/iter
          </div>
        </div>

        {/* Objectives — Committed then Uncommitted, stacked vertically */}
        <div className="team-section__objectives">
          <div className="team-section__subtitle">PI Objectives (BV: {totalBV})</div>
          <div className="team-section__obj-section">
            <div className="team-section__obj-label">Committed</div>
            {committed.map((o: PIObjective, i: number) => (
              <div key={i} className="team-section__obj-card">
                <span className="team-section__obj-num">{i + 1}</span>
                <span className="team-section__obj-title">{o.title}</span>
                <span className="team-section__obj-bv">BV {o.bv}</span>
              </div>
            ))}
            {committed.length === 0 && <span className="team-section__empty">No committed objectives</span>}
          </div>
          <div className="team-section__obj-section">
            <div className="team-section__obj-label team-section__obj-label--uncommitted">Uncommitted</div>
            {stretch.map((o: PIObjective, i: number) => (
              <div key={i} className="team-section__obj-card team-section__obj-card--uncommitted">
                <span className="team-section__obj-num">{committed.length + i + 1}</span>
                <span className="team-section__obj-title">{o.title}</span>
                <span className="team-section__obj-bv">BV {o.bv}</span>
              </div>
            ))}
            {stretch.length === 0 && <span className="team-section__empty">No uncommitted objectives</span>}
          </div>
        </div>
      </div>

      {/* Middle: Risks + Confidence */}
      <div className="team-section__middle">
        <div className="team-section__risks">
          <div className="team-section__subtitle">Risks</div>
          <div className="team-section__risk-cards">
            {teamRisks.slice(0, 6).map(r => (
              <div key={r.id} className={`team-section__risk-card team-section__risk-card--${r.severity || 'medium'}`}>
                <span>{r.id}</span>
                <span>{r.title}</span>
              </div>
            ))}
            {teamRisks.length === 0 && <span className="team-section__empty">No risks</span>}
          </div>
        </div>
        <div className="team-section__confidence">
          <div className="team-section__subtitle">Confidence Vote</div>
          <div className="team-section__conf-value" style={{
            color: confidence >= 4 ? '#059669' : confidence === 3 ? '#d97706' : '#dc2626',
          }}>
            {confidence || '—'}
          </div>
          <div className="team-section__conf-label">/ 5</div>
        </div>
      </div>

      {/* Bottom: Iteration grid */}
      <div className="team-section__iterations">
        <div className="team-section__subtitle">Iteration Backlog</div>
        <div className="team-section__iter-grid" style={{
          gridTemplateColumns: `repeat(${iterations.length}, 1fr)`,
        }}>
          {iterations.map(iter => {
            const stories = storiesByIter[iter.id] || [];
            const load = stories.reduce((s, i) => s + (i.js || 0), 0);
            return (
              <div key={iter.id} className={`team-section__iter-col ${iter.type === 'IP' ? 'team-section__iter-col--ip' : ''}`}>
                <div className="team-section__iter-header">
                  <span className="team-section__iter-id">{iter.id.split('.').pop()}</span>
                  <span className="team-section__iter-load">
                    {load}/{totalCapacity}
                  </span>
                </div>
                {stories.map(s => (
                  <div key={s.id} className="team-section__story-card">
                    <span className="team-section__story-id">{s.id}</span>
                    <span className="team-section__story-title">{s.title}</span>
                    <span className="team-section__story-js">JS {s.js}</span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
