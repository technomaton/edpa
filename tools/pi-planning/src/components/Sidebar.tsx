import { NavLink } from 'react-router-dom';
import { useConfigStore } from '../store/config-store';

const NAV = [
  { to: '/', label: 'Program Board', icon: '▦' },
  { to: '/team', label: 'Team Board', icon: '⊞' },
  { to: '/prioritize', label: 'Prioritization', icon: '⇅' },
  { to: '/people', label: 'People', icon: '⊕' },
];

const PI_STATUS_LABELS: Record<string, string> = {
  planning: 'Planning',
  active: 'Active',
  closed: 'Closed',
};

export function Sidebar() {
  const project = useConfigStore(s => s.project);
  const selectedPI = useConfigStore(s => s.selectedPI);
  const availablePIs = useConfigStore(s => s.availablePIs);
  const isReadonly = useConfigStore(s => s.isReadonly);
  const selectPI = useConfigStore(s => s.selectPI);

  const currentInfo = availablePIs.find(p => p.id === selectedPI);
  const activeIter = currentInfo?.iterations.find(it => it.status === 'active');
  const closedCount = currentInfo?.iterations.filter(it => it.status === 'closed').length || 0;
  const totalCount = currentInfo?.iterations.length || 0;

  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <span className="sidebar__logo">EDPA</span>
        <span className="sidebar__sub">PI Planning</span>
      </div>

      {/* Project info */}
      {project && (
        <div className="sidebar__project">
          <div className="sidebar__project-name">{project.name}</div>
        </div>
      )}

      {/* PI Selector */}
      <div className="pi-selector">
        <div className="pi-selector__label">Planning Interval</div>
        <div className="pi-selector__list">
          {availablePIs.map(pi => (
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

        {/* Current PI details */}
        {currentInfo && (
          <div className="pi-info">
            <div className="pi-info__progress">
              <span className="pi-info__iter-count">
                {closedCount}/{totalCount} iterations
              </span>
              <div className="pi-info__bar">
                <div
                  className="pi-info__bar-fill"
                  style={{ width: `${totalCount > 0 ? (closedCount / totalCount) * 100 : 0}%` }}
                />
              </div>
            </div>
            {activeIter && (
              <div className="pi-info__active">
                <span className="pi-info__active-dot" />
                {activeIter.id.split('.').pop()} &middot; {activeIter.dates}
              </div>
            )}
            {isReadonly && (
              <div className="pi-info__readonly">Read-only</div>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="sidebar__nav">
        {NAV.map(n => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === '/'}
            className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}
          >
            <span className="sidebar__icon">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
