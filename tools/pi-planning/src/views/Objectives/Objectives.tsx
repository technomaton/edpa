import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useConfigStore } from '../../store/config-store';
import { api } from '../../lib/api';
import type { ObjStatus, PIObjective, ObjectivesData } from '../../types/edpa';

const STATUS_LABELS: Record<ObjStatus, string> = {
  done: 'Done',
  in_progress: 'In Progress',
  planned: 'Planned',
};

const STATUS_CYCLE: ObjStatus[] = ['planned', 'in_progress', 'done'];

function confidenceColor(c: number): string {
  if (c < 3) return 'var(--rd)';
  if (c === 3) return 'var(--yl)';
  return 'var(--gn)';
}

function statusClass(s: ObjStatus): string {
  if (s === 'done') return 'obj-status--done';
  if (s === 'in_progress') return 'obj-status--ip';
  return 'obj-status--planned';
}

function sumBv(objectives: PIObjective[]): number {
  return objectives.reduce((s, o) => s + o.bv, 0);
}

export function Objectives() {
  const selectedPI = useConfigStore(s => s.selectedPI);
  const isReadonly = useConfigStore(s => s.isReadonly);
  const [data, setData] = useState<ObjectivesData | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!selectedPI) return;
    const result = await api.getObjectives(selectedPI);
    setData(result);
  }, [selectedPI]);

  useEffect(() => { load(); }, [load]);

  const saveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const save = useCallback((updated: ObjectivesData) => {
    setData(updated);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      setSaving(true);
      await api.saveObjectives(updated.pi, updated);
      setSaving(false);
    }, 400);
  }, []);

  const updateObjective = useCallback(
    (teamId: string, kind: 'committed' | 'stretch', index: number, patch: Partial<PIObjective>) => {
      if (!data) return;
      const updated = structuredClone(data);
      const obj = updated.teams[teamId][kind][index];
      Object.assign(obj, patch);
      save(updated);
    },
    [data, save],
  );

  const addObjective = useCallback(
    (teamId: string, kind: 'committed' | 'stretch') => {
      if (!data) return;
      const updated = structuredClone(data);
      updated.teams[teamId][kind].push({ title: '', bv: 5, status: 'planned' });
      save(updated);
    },
    [data, save],
  );

  const removeObjective = useCallback(
    (teamId: string, kind: 'committed' | 'stretch', index: number) => {
      if (!data) return;
      const updated = structuredClone(data);
      updated.teams[teamId][kind].splice(index, 1);
      save(updated);
    },
    [data, save],
  );

  const setConfidence = useCallback(
    (teamId: string, value: number) => {
      if (!data) return;
      const updated = structuredClone(data);
      updated.teams[teamId].confidence = value;
      save(updated);
    },
    [data, save],
  );

  const addTeam = useCallback(() => {
    if (!data) return;
    const name = prompt('Team name:');
    if (!name) return;
    const updated = structuredClone(data);
    updated.teams[name] = { committed: [], stretch: [], confidence: 3 };
    save(updated);
  }, [data, save]);

  const avgConfidence = useMemo(() => {
    if (!data) return 0;
    const teams = Object.values(data.teams);
    if (teams.length === 0) return 0;
    return teams.reduce((s, t) => s + t.confidence, 0) / teams.length;
  }, [data]);

  if (!data) {
    return <div className="obj-view"><span className="obj-empty">Loading objectives...</span></div>;
  }

  const teamEntries = Object.entries(data.teams);

  return (
    <div className="obj-view">
      <div className="obj-header">
        <h2 className="obj-header__title">PI Objectives</h2>
        <span className="obj-header__pi">{data.pi}</span>
        {saving && <span className="obj-header__saving">Saving...</span>}
      </div>

      {teamEntries.length === 0 && (
        <div className="obj-empty">No teams defined. Add a team to get started.</div>
      )}

      {teamEntries.map(([teamId, team]) => (
        <div key={teamId} className="obj-team">
          <div className="obj-team__header">
            <span className="obj-team__name">{teamId}</span>
            <span
              className="obj-team__confidence"
              style={{ background: confidenceColor(team.confidence) }}
              title="Team confidence vote (1-5)"
            >
              {team.confidence}/5
            </span>
            {!isReadonly && (
              <div className="obj-confidence-btns">
                {[1, 2, 3, 4, 5].map(v => (
                  <button
                    key={v}
                    className={`obj-confidence-btn ${v === team.confidence ? 'obj-confidence-btn--active' : ''}`}
                    onClick={() => setConfidence(teamId, v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="obj-columns">
            {(['committed', 'stretch'] as const).map(kind => (
              <div key={kind} className="obj-col">
                <div className="obj-col__header">
                  <span className="obj-col__label">
                    {kind === 'committed' ? 'Committed' : 'Stretch'}
                  </span>
                  <span className="obj-col__total">BV: {sumBv(team[kind])}</span>
                </div>

                {team[kind].map((obj, i) => (
                  <div key={i} className="obj-card">
                    <input
                      className="obj-card__title"
                      value={obj.title}
                      placeholder="Objective title..."
                      disabled={isReadonly}
                      onChange={e => updateObjective(teamId, kind, i, { title: e.target.value })}
                    />
                    <div className="obj-card__meta">
                      <label className="obj-card__bv-label">
                        BV
                        <input
                          type="number"
                          className="obj-card__bv"
                          value={obj.bv}
                          min={1}
                          max={10}
                          disabled={isReadonly}
                          onChange={e => updateObjective(teamId, kind, i, { bv: parseInt(e.target.value) || 1 })}
                        />
                      </label>
                      <button
                        className={`obj-card__status ${statusClass(obj.status)}`}
                        disabled={isReadonly}
                        onClick={() => {
                          const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(obj.status) + 1) % STATUS_CYCLE.length];
                          updateObjective(teamId, kind, i, { status: next });
                        }}
                      >
                        {STATUS_LABELS[obj.status]}
                      </button>
                      {!isReadonly && (
                        <button
                          className="obj-card__remove"
                          title="Remove objective"
                          onClick={() => removeObjective(teamId, kind, i)}
                        >
                          x
                        </button>
                      )}
                    </div>
                  </div>
                ))}

                {!isReadonly && (
                  <button className="obj-add" onClick={() => addObjective(teamId, kind)}>
                    + Add objective
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {!isReadonly && (
        <button className="obj-add-team" onClick={addTeam}>+ Add team</button>
      )}

      <div className="obj-footer">
        <span className="obj-footer__label">PI Predictability</span>
        <span
          className="obj-footer__value"
          style={{ color: confidenceColor(Math.round(avgConfidence)) }}
        >
          {avgConfidence.toFixed(1)} / 5
        </span>
        <span className="obj-footer__desc">Average team confidence</span>
      </div>
    </div>
  );
}
