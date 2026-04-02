import { useState, useMemo } from 'react';
import type { WorkItem, ItemStatus, Iteration } from '../types/edpa';

interface ItemEditorProps {
  item: WorkItem;
  iterations: Iteration[];
  people: string[];
  onSave: (updated: WorkItem) => void;
  onClose: () => void;
  readonly?: boolean;
}

const STATUS_OPTIONS: ItemStatus[] = ['Planned', 'In Progress', 'Active', 'Done'];
const HALF_OPTIONS: { value: 1 | 2; label: string }[] = [
  { value: 1, label: '1 (W1)' },
  { value: 2, label: '2 (W2)' },
];

const TYPE_FG: Record<string, string> = {
  Initiative: '#db2777', Epic: '#6366f1', Feature: '#0891b2',
  Story: '#ea580c', Defect: '#dc2626',
};

export function ItemEditor({ item, iterations, people, onSave, onClose, readonly }: ItemEditorProps) {
  const [draft, setDraft] = useState<WorkItem>({ ...item });

  const wsjf = useMemo(() => {
    const { bv, tc, rr, js } = draft;
    if (js && js > 0 && bv != null && tc != null && rr != null) {
      return ((bv + tc + rr) / js).toFixed(2);
    }
    return '-';
  }, [draft.bv, draft.tc, draft.rr, draft.js]);

  const set = <K extends keyof WorkItem>(key: K, value: WorkItem[K]) => {
    setDraft(prev => ({ ...prev, [key]: value }));
  };

  const setNum = (key: 'js' | 'bv' | 'tc' | 'rr', raw: string) => {
    const n = raw === '' ? 0 : Number(raw);
    if (!isNaN(n)) set(key, n);
  };

  return (
    <div className="item-editor">
      <div className="item-editor__header">
        <span className="item-editor__id" style={{ color: TYPE_FG[item.type] }}>{item.id}</span>
        <button className="item-editor__close" onClick={onClose}>X</button>
      </div>

      <div className="item-editor__field">
        <label className="item-editor__label">Title</label>
        <input
          className="item-editor__input"
          value={draft.title}
          onChange={e => set('title', e.target.value)}
          disabled={readonly}
        />
      </div>

      <div className="item-editor__grid">
        <div className="item-editor__field">
          <label className="item-editor__label">Status</label>
          <select
            className="item-editor__select"
            value={draft.status}
            onChange={e => set('status', e.target.value as ItemStatus)}
            disabled={readonly}
          >
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">Iteration</label>
          <select
            className="item-editor__select"
            value={draft.iteration || ''}
            onChange={e => set('iteration', e.target.value || undefined)}
            disabled={readonly}
          >
            <option value="">-</option>
            {iterations.map(it => (
              <option key={it.id} value={it.id}>{it.id}</option>
            ))}
          </select>
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">Half</label>
          <select
            className="item-editor__select"
            value={draft.iteration_half || 1}
            onChange={e => set('iteration_half', Number(e.target.value) as 1 | 2)}
            disabled={readonly}
          >
            {HALF_OPTIONS.map(h => (
              <option key={h.value} value={h.value}>{h.label}</option>
            ))}
          </select>
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">Owner</label>
          {people.length > 0 ? (
            <select
              className="item-editor__select"
              value={draft.owner || draft.assignee || ''}
              onChange={e => set('owner', e.target.value || undefined)}
              disabled={readonly}
            >
              <option value="">-</option>
              {people.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          ) : (
            <input
              className="item-editor__input"
              value={draft.owner || draft.assignee || ''}
              onChange={e => set('owner', e.target.value || undefined)}
              disabled={readonly}
            />
          )}
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">Job Size</label>
          <input
            className="item-editor__input item-editor__input--num"
            type="number"
            min={0}
            value={draft.js}
            onChange={e => setNum('js', e.target.value)}
            disabled={readonly}
          />
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">BV</label>
          <input
            className="item-editor__input item-editor__input--num"
            type="number"
            min={0}
            value={draft.bv ?? ''}
            onChange={e => setNum('bv', e.target.value)}
            disabled={readonly}
          />
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">TC</label>
          <input
            className="item-editor__input item-editor__input--num"
            type="number"
            min={0}
            value={draft.tc ?? ''}
            onChange={e => setNum('tc', e.target.value)}
            disabled={readonly}
          />
        </div>

        <div className="item-editor__field">
          <label className="item-editor__label">RR</label>
          <input
            className="item-editor__input item-editor__input--num"
            type="number"
            min={0}
            value={draft.rr ?? ''}
            onChange={e => setNum('rr', e.target.value)}
            disabled={readonly}
          />
        </div>

        <div className="item-editor__field item-editor__field--wsjf">
          <label className="item-editor__label">WSJF</label>
          <span className="item-editor__wsjf">{wsjf}</span>
        </div>
      </div>

      {item.contributors && item.contributors.length > 0 && (
        <div className="item-editor__contributors">
          <span className="item-editor__label">Contributors</span>
          {item.contributors.map((c, i) => (
            <div key={i} className="detail-contributor">
              <span>{c.person}</span>
              <span className="detail-contributor__role">{c.role}</span>
              <span className="detail-contributor__cw">CW {c.cw}</span>
            </div>
          ))}
        </div>
      )}

      {!readonly && (
        <div className="item-editor__actions">
          <button className="item-editor__btn item-editor__btn--cancel" onClick={onClose}>Cancel</button>
          <button className="item-editor__btn item-editor__btn--save" onClick={() => onSave(draft)}>Save</button>
        </div>
      )}
    </div>
  );
}
