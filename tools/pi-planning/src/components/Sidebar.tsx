import { useState } from 'react';
import { useConfigStore } from '../store/config-store';

const PI_STATUS_LABELS: Record<string, string> = {
  planning: 'Planning',
  active: 'Active',
  closed: 'Closed',
};

function zoomTo(sectionId: string) {
  const fn = (window as unknown as Record<string, unknown>).__piCanvasZoomTo;
  if (typeof fn === 'function') fn(sectionId);
}

export function Sidebar() {
  const project = useConfigStore(s => s.project);
  const pis = useConfigStore(s => s.pis);
  const people = useConfigStore(s => s.people);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const isReadonly = useConfigStore(s => s.isReadonly);
  const selectPI = useConfigStore(s => s.selectPI);
  const [activeSection, setActiveSection] = useState('program-board');

  const currentInfo = pis.find(p => p.id === selectedPI);
  const activeIter = currentInfo?.iterations.find(it => it.status === 'active');
  const closedCount = currentInfo?.iterations.filter(it => it.status === 'closed').length || 0;
  const totalCount = currentInfo?.iterations.length || 0;
  const teamIds = [...new Set(people.map(p => p.team))];

  const handleZoom = (id: string) => {
    setActiveSection(id);
    zoomTo(id);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <span className="sidebar__logo">EDPA</span>
        <span className="sidebar__sub">PI Planning</span>
      </div>

      {project && (
        <div className="sidebar__project">
          <div className="sidebar__project-name">{project.name}</div>
        </div>
      )}

      {/* PI Selector */}
      <div className="pi-selector">
        <div className="pi-selector__label">Planning Interval</div>
        <div className="pi-selector__list">
          {pis.map(pi => (
            <button
              key={pi.id}
              className={`pi-selector__item ${pi.id === selectedPI ? 'pi-selector__item--active' : ''}`}
              onClick={() => selectPI(pi.id)}
            >
              <span className={`pi-selector__dot pi-selector__dot--${pi.status}`} />
              <span className="pi-selector__id">{pi.id}</span>
              <span className={`pi-selector__status pi-selector__status--${pi.status}`}>
                {PI_STATUS_LABELS[pi.status]}
              </span>
            </button>
          ))}
        </div>
        {currentInfo && (
          <div className="pi-info">
            <div className="pi-info__progress">
              <span className="pi-info__iter-count">{closedCount}/{totalCount} iterations</span>
              <div className="pi-info__bar">
                <div className="pi-info__bar-fill" style={{ width: `${totalCount > 0 ? (closedCount / totalCount) * 100 : 0}%` }} />
              </div>
            </div>
            {activeIter && (
              <div className="pi-info__active">
                <span className="pi-info__active-dot" />
                {activeIter.id.split('.').pop()} &middot; {activeIter.dates}
              </div>
            )}
            {isReadonly && <div className="pi-info__readonly">Read-only</div>}
          </div>
        )}
      </div>

      {/* Canvas Navigation — zoom shortcuts */}
      <nav className="sidebar__nav">
        <div className="sidebar__nav-label">Sections</div>
        <button
          className={`sidebar__link ${activeSection === 'program-board' ? 'sidebar__link--active' : ''}`}
          onClick={() => handleZoom('program-board')}
        >
          <span className="sidebar__icon">▦</span> Program Board
        </button>

        <div className="sidebar__nav-label">Teams</div>
        {teamIds.map(t => (
          <button
            key={t}
            className={`sidebar__link ${activeSection === `team-${t}` ? 'sidebar__link--active' : ''}`}
            onClick={() => handleZoom(`team-${t}`)}
          >
            <span className="sidebar__icon">⊞</span> {t}
          </button>
        ))}

        <div className="sidebar__nav-label">Tools</div>
        <button
          className={`sidebar__link ${activeSection === 'roam' ? 'sidebar__link--active' : ''}`}
          onClick={() => handleZoom('roam')}
        >
          <span className="sidebar__icon">⚠</span> ROAM Board
        </button>
        <button
          className={`sidebar__link ${activeSection === 'prioritization' ? 'sidebar__link--active' : ''}`}
          onClick={() => handleZoom('prioritization')}
        >
          <span className="sidebar__icon">⇅</span> Prioritization
        </button>
        <button
          className={`sidebar__link ${activeSection === 'calendar' ? 'sidebar__link--active' : ''}`}
          onClick={() => handleZoom('calendar')}
        >
          <span className="sidebar__icon">◫</span> Calendar
        </button>
      </nav>
    </aside>
  );
}
