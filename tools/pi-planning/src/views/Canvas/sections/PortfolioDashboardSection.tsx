import { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import type { WorkItem, ProjectConfig } from '../../../types/edpa';
import type { Person } from '../../../types/edpa';

interface Props {
  items: unknown[];
  people: unknown[];
  project: unknown;
  width: number;
  height: number;
}

const CLR: Record<string, string> = {
  Initiative: '#db2777', Epic: '#6366f1', Feature: '#0891b2', Story: '#ea580c',
};

interface Pt { cx: number; top: number; bot: number }

function off(el: HTMLElement, root: HTMLElement) {
  let t = 0, l = 0;
  let cur: HTMLElement | null = el;
  while (cur && cur !== root) {
    t += cur.offsetTop - cur.scrollTop;
    l += cur.offsetLeft - cur.scrollLeft;
    cur = cur.offsetParent as HTMLElement | null;
  }
  return { t, l, w: el.offsetWidth, h: el.offsetHeight };
}

export function PortfolioDashboardSection({ items: rawItems, people: rawPeople, project: rawProject, width, height }: Props) {
  const items = rawItems as WorkItem[];
  const _people = rawPeople as Person[];
  const project = rawProject as ProjectConfig | null;
  const rootRef = useRef<HTMLDivElement>(null);
  const [pts, setPts] = useState<Map<string, Pt>>(new Map());
  const [svgW, setSvgW] = useState(0);
  const [svgH, setSvgH] = useState(0);

  const initiatives = useMemo(() => items.filter(i => i.type === 'Initiative'), [items]);
  const kids = useCallback((pid: string, type: string) =>
    items.filter(i => i.parent === pid && i.type === type), [items]);

  const storyCount = useCallback((featId: string): number =>
    Math.max(kids(featId, 'Story').length, 1), [kids]);

  const epicWeight = useCallback((epicId: string): number =>
    kids(epicId, 'Feature').reduce((s, f) => s + storyCount(f.id), 0) || 1, [kids, storyCount]);

  const initWeight = useCallback((initId: string): number =>
    kids(initId, 'Epic').reduce((s, e) => s + epicWeight(e.id), 0) || 1, [kids, epicWeight]);

  const pairs = useMemo(() =>
    items.filter(i => i.parent && items.some(x => x.id === i.parent))
      .map(i => ({ p: i.parent!, c: i.id })), [items]);

  const measure = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    const map = new Map<string, Pt>();
    root.querySelectorAll<HTMLElement>('[data-cid]').forEach(el => {
      const o = off(el, root);
      map.set(el.dataset.cid!, { cx: o.l + o.w / 2, top: o.t, bot: o.t + o.h });
    });
    setPts(map);
    setSvgW(root.scrollWidth);
    setSvgH(root.scrollHeight);
  }, []);

  useEffect(() => {
    const ts = [80, 250, 600, 1200].map(d => setTimeout(measure, d));
    const ro = new ResizeObserver(measure);
    if (rootRef.current) ro.observe(rootRef.current);
    return () => { ts.forEach(clearTimeout); ro.disconnect(); };
  }, [items, _people, measure]);

  const lines = useMemo(() => {
    if (pts.size === 0) return [];
    return pairs.map(({ p, c }) => {
      const pp = pts.get(p), cp = pts.get(c);
      if (!pp || !cp) return null;
      const item = items.find(i => i.id === p);
      return { x1: pp.cx, y1: pp.bot, x2: cp.cx, y2: cp.top, clr: CLR[item?.type || ''] || '#94a3b8', k: `${p}-${c}` };
    }).filter(Boolean) as { x1: number; y1: number; x2: number; y2: number; clr: string; k: string }[];
  }, [pts, pairs, items]);

  const card = (item: WorkItem) => (
    <div data-cid={item.id} className="pt-card" style={{ borderLeftColor: CLR[item.type] }}>
      <span className="pt-card__id" style={{ color: CLR[item.type] }}>{item.id}</span>
      <span className="pt-card__title">{item.title}</span>
      <span className="pt-card__status">{item.status}</span>
    </div>
  );

  return (
    <div ref={rootRef} className="pt-root" style={{ width, minHeight: height }}>
      {/* Strategic Board */}
      <div className="pt-strategic">
        <div className="pt-strategic__lbl">Strategic<br/>Board</div>
        <div className="pt-strategic__body">
          <div className="pt-strategic__vision" data-cid="enterprise">
            <span className="pt-strategic__vision-title">{project?.name || 'Project'}</span>
            <span className="pt-strategic__vision-sub">Ultimate Objectives — Vision (Why)</span>
          </div>
          <div className="pt-strategic__themes">
            <span className="pt-strategic__themes-title">Strategic Themes (What and How)</span>
            <span className="pt-strategic__themes-sub">Objectives + OKR + KPI</span>
          </div>
        </div>
      </div>

      {/* Initiative → Epic → Feature → Story: nested tree */}
      <div className="pt-bands">
        {/* Row 1: Initiatives */}
        <div className="pt-bands__lbl" style={{ background: 'var(--pk)' }}>Initiatives</div>
        <div className="pt-brow pt-brow--init">
          {initiatives.map(init => (
            <div key={init.id} className="pt-bcell">
              {card(init)}
            </div>
          ))}
        </div>

        {/* Row 2: Epics */}
        <div className="pt-bands__lbl" style={{ background: 'var(--ac)' }}>Epics</div>
        <div className="pt-brow pt-brow--epic">
          {initiatives.map(init =>
            kids(init.id, 'Epic').map(epic => (
              <div key={epic.id} className="pt-bcell">
                {card(epic)}
              </div>
            ))
          )}
        </div>

        {/* Row 3: Features — grouped under parent Epic */}
        <div className="pt-bands__lbl" style={{ background: 'var(--cy)' }}>Features</div>
        <div className="pt-brow pt-brow--feat">
          {initiatives.map(init =>
            kids(init.id, 'Epic').map(epic => (
              <div key={`fg-${epic.id}`} className="pt-fgroup">
                {kids(epic.id, 'Feature').map(feat => (
                  <div key={feat.id} className="pt-bcell">{card(feat)}</div>
                ))}
              </div>
            ))
          )}
        </div>

        {/* Row 4: Stories — grouped under parent Feature, stacked vertically */}
        <div className="pt-bands__lbl" style={{ background: 'var(--or)' }}>Stories</div>
        <div className="pt-brow pt-brow--story">
          {initiatives.map(init =>
            kids(init.id, 'Epic').map(epic => (
              <div key={`sg-${epic.id}`} className="pt-fgroup">
                {kids(epic.id, 'Feature').map(feat => (
                  <div key={`sc-${feat.id}`} className="pt-sstack">
                    {kids(feat.id, 'Story').map(s => (
                      <div key={s.id} className="pt-bcell">{card(s)}</div>
                    ))}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </div>

      {/* SVG connectors */}
      {svgW > 0 && (
        <svg width={svgW} height={svgH} viewBox={`0 0 ${svgW} ${svgH}`}
          style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none', zIndex: 10 }}>
          {lines.map(({ x1, y1, x2, y2, clr, k }) => {
            const my = (y1 + y2) / 2;
            return <path key={k} d={`M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`}
              fill="none" stroke={clr} strokeWidth={2} opacity={0.4} />;
          })}
        </svg>
      )}
    </div>
  );
}
