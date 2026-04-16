import { useMemo, useRef, useLayoutEffect, useState } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem } from '../../types/edpa';
import { DashboardBand } from './DashboardBand';
import { HierarchyConnectors } from './HierarchyConnectors';

interface CardPosition {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  band: string;
}

export function PortfolioDashboard() {
  const items = useBacklogStore(s => s.items);
  const project = useConfigStore(s => s.project);
  const people = useConfigStore(s => s.people);
  const containerRef = useRef<HTMLDivElement>(null);
  const [cardPositions, setCardPositions] = useState<CardPosition[]>([]);

  const initiatives = useMemo(() => items.filter(i => i.type === 'Initiative'), [items]);
  const epics = useMemo(() => items.filter(i => i.type === 'Epic'), [items]);
  const features = useMemo(() => items.filter(i => i.type === 'Feature'), [items]);
  const stories = useMemo(() => items.filter(i => i.type === 'Story'), [items]);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const storiesByTeam = useMemo(() => {
    const map: Record<string, WorkItem[]> = {};
    for (const t of teamIds) map[t] = [];
    for (const s of stories) {
      const person = people.find(p => p.id === (s.assignee || s.owner));
      const team = person?.team || 'unassigned';
      if (!map[team]) map[team] = [];
      map[team].push(s);
    }
    return map;
  }, [stories, people, teamIds]);

  const parentChildPairs = useMemo(() => {
    const pairs: { parentId: string; childId: string }[] = [];
    for (const item of items) {
      if (item.parent) {
        pairs.push({ parentId: item.parent, childId: item.id });
      }
    }
    return pairs;
  }, [items]);

  useLayoutEffect(() => {
    if (!containerRef.current) return;
    const positions: CardPosition[] = [];
    const cards = containerRef.current.querySelectorAll('[data-card-id]');
    const containerRect = containerRef.current.getBoundingClientRect();
    cards.forEach(el => {
      const id = el.getAttribute('data-card-id')!;
      const band = el.getAttribute('data-band')!;
      const rect = el.getBoundingClientRect();
      positions.push({
        id, band,
        x: rect.left - containerRect.left + rect.width / 2,
        y: rect.top - containerRect.top + rect.height / 2,
        width: rect.width,
        height: rect.height,
      });
    });
    setCardPositions(positions);
  }, [items, people]);

  return (
    <div className="portfolio-dashboard" ref={containerRef}>
      <div className="portfolio-dashboard__header">
        <h2 className="portfolio-dashboard__title">Portfolio Dashboard</h2>
        <span className="portfolio-dashboard__sub">SAFe 6 — Hierarchy Visualization</span>
      </div>

      <div className="portfolio-dashboard__bands">
        <DashboardBand
          band="enterprise"
          label="Enterprise"
          sublabel="North Star Strategy"
          color="#db2777"
        >
          <div className="portfolio-card portfolio-card--enterprise" data-card-id="enterprise" data-band="enterprise">
            <div className="portfolio-card__title">{project?.name || 'Project'}</div>
            {project?.organization && (
              <div className="portfolio-card__sub">{project.organization}</div>
            )}
          </div>
        </DashboardBand>

        <DashboardBand
          band="portfolio"
          label="Portfolio"
          sublabel={`${initiatives.length} Initiatives`}
          color="#6366f1"
        >
          {initiatives.map(item => (
            <div key={item.id} className="portfolio-card portfolio-card--initiative" data-card-id={item.id} data-band="portfolio">
              <div className="portfolio-card__head">
                <span className="portfolio-card__id">{item.id}</span>
                <span className="portfolio-card__status">{item.status}</span>
              </div>
              <div className="portfolio-card__title">{item.title}</div>
            </div>
          ))}
        </DashboardBand>

        <DashboardBand
          band="program"
          label="Program"
          sublabel={`${epics.length} Epics · ${features.length} Features`}
          color="#059669"
        >
          {epics.map(item => (
            <div key={item.id} className="portfolio-card portfolio-card--epic" data-card-id={item.id} data-band="program">
              <div className="portfolio-card__head">
                <span className="portfolio-card__id">{item.id}</span>
                {item.epic_type && (
                  <span className={`portfolio-card__badge portfolio-card__badge--${item.epic_type.toLowerCase()}`}>
                    {item.epic_type}
                  </span>
                )}
              </div>
              <div className="portfolio-card__title">{item.title}</div>
              <div className="portfolio-card__foot">
                <span className="portfolio-card__status">{item.status}</span>
                {item.wsjf != null && <span className="portfolio-card__wsjf">WSJF {item.wsjf.toFixed(1)}</span>}
              </div>
            </div>
          ))}
          {features.map(item => (
            <div key={item.id} className="portfolio-card portfolio-card--feature" data-card-id={item.id} data-band="program">
              <div className="portfolio-card__head">
                <span className="portfolio-card__id">{item.id}</span>
              </div>
              <div className="portfolio-card__title">{item.title}</div>
              <div className="portfolio-card__foot">
                <span className="portfolio-card__status">{item.status}</span>
                {item.iteration && <span className="portfolio-card__iter">{item.iteration}</span>}
              </div>
            </div>
          ))}
        </DashboardBand>

        <DashboardBand
          band="team"
          label="Team / ART"
          sublabel={`${stories.length} Stories · ${teamIds.length} Teams`}
          color="#ea580c"
        >
          {teamIds.map(teamId => (
            <div key={teamId} className="portfolio-team-group">
              <div className="portfolio-team-group__label">{teamId}</div>
              <div className="portfolio-team-group__cards">
                {(storiesByTeam[teamId] || []).map(item => (
                  <div key={item.id} className="portfolio-card portfolio-card--story" data-card-id={item.id} data-band="team">
                    <span className="portfolio-card__id">{item.id}</span>
                    <span className="portfolio-card__title-sm">{item.title}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </DashboardBand>
      </div>

      <HierarchyConnectors
        positions={cardPositions}
        pairs={parentChildPairs}
      />
    </div>
  );
}
