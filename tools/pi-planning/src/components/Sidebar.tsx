import { NavLink } from 'react-router-dom';
import { useConfigStore } from '../store/config-store';

const NAV = [
  { to: '/', label: 'Program Board', icon: '▦' },
  { to: '/team', label: 'Team Board', icon: '⊞' },
  { to: '/prioritize', label: 'Prioritization', icon: '⇅' },
  { to: '/people', label: 'People', icon: '⊕' },
];

export function Sidebar() {
  const project = useConfigStore(s => s.project);
  const pi = useConfigStore(s => s.pi);

  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <span className="sidebar__logo">EDPA</span>
        <span className="sidebar__sub">PI Planning</span>
      </div>
      {project && (
        <div className="sidebar__project">
          <div className="sidebar__project-name">{project.name}</div>
          {pi && <div className="sidebar__pi">{pi.current}</div>}
        </div>
      )}
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
