import { Fragment, useMemo, useState, type DragEvent } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';
import type { WorkItem, Iteration } from '../../types/edpa';

// -- Helpers ------------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  Story: '#ea580c', Feature: '#0891b2', Defect: '#dc2626',
};

const STATUS_COLORS: Record<string, string> = {
  Done: '#059669', 'In Progress': '#6366f1', Active: '#6366f1', Planned: '#8892a8',
};

function iterMatch(item: WorkItem, iter: Iteration): boolean {
  return !!item.iteration && item.iteration.startsWith(iter.id);
}

// -- Story Card ---------------------------------------------------------------

function StoryCard({ item }: { item: WorkItem }) {
  const color = TYPE_COLORS[item.type] || '#8892a8';
  const isDone = item.status === 'Done';

  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData('text/plain', item.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div
      className="tb-card"
      draggable
      onDragStart={onDragStart}
      style={{ borderLeftColor: color, opacity: isDone ? 0.5 : 1 }}
    >
      <div className="tb-card__head">
        <span className="tb-card__id" style={{ color }}>{item.id}</span>
        {item.js != null && <span className="tb-card__js">JS {item.js}</span>}
      </div>
      <div className="tb-card__title">{item.title}</div>
      <div className="tb-card__foot">
        <span className="tb-card__assignee">{item.assignee || '-'}</span>
        <span className="tb-card__status" style={{ color: STATUS_COLORS[item.status] }}>{item.status}</span>
      </div>
    </div>
  );
}

// -- Table Row ----------------------------------------------------------------

function TableRow({ item }: { item: WorkItem }) {
  const isDone = item.status === 'Done';
  return (
    <tr className={`tb-table__row ${isDone ? 'tb-table__row--done' : ''}`}>
      <td className="tb-table__td tb-table__td--id">{item.id}</td>
      <td className="tb-table__td">{item.title}</td>
      <td className="tb-table__td tb-table__td--num">{item.js ?? '-'}</td>
      <td className="tb-table__td">{item.assignee || '-'}</td>
      <td className="tb-table__td" style={{ color: STATUS_COLORS[item.status] }}>{item.status}</td>
    </tr>
  );
}

// -- Iteration Cell -----------------------------------------------------------

function IterCell({
  iterationId,
  items,
  viewMode,
  onDrop,
  isIP,
}: {
  iterationId: string;
  items: WorkItem[];
  viewMode: 'cards' | 'table';
  onDrop: (itemId: string, iteration: string) => void;
  isIP: boolean;
}) {
  const [dragOver, setDragOver] = useState(false);
  const totalJs = items.reduce((s, i) => s + (i.js || 0), 0);

  return (
    <div
      className={`tb-cell ${dragOver ? 'tb-cell--drag-over' : ''} ${isIP ? 'tb-cell--ip' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault();
        setDragOver(false);
        if (isIP) return;
        const id = e.dataTransfer.getData('text/plain');
        if (id) onDrop(id, iterationId);
      }}
    >
      {viewMode === 'cards' ? (
        <div className="tb-cell__cards">
          {items.map(item => <StoryCard key={item.id} item={item} />)}
        </div>
      ) : (
        items.length > 0 ? (
          <table className="tb-table"><tbody>
            {items.map(item => <TableRow key={item.id} item={item} />)}
          </tbody></table>
        ) : null
      )}
      {totalJs > 0 && (
        <div className="tb-cell__summary">
          <span className="tb-cell__summary-label">{items.length} items</span>
          <span className="tb-cell__summary-js">JS {totalJs}</span>
        </div>
      )}
    </div>
  );
}

// -- Feature Group Header (row header) ----------------------------------------

function FeatureHeader({ feature, storyCount }: { feature: WorkItem | null; storyCount: number }) {
  if (!feature) {
    return (
      <div className="tb-row-header tb-row-header--unassigned">
        <span className="tb-row-header__name">Unassigned</span>
        <span className="tb-row-header__role">{storyCount} items</span>
      </div>
    );
  }

  const color = TYPE_COLORS[feature.type] || '#0891b2';
  return (
    <div className="tb-row-header tb-row-header--feature">
      <span className="tb-row-header__fid" style={{ color }}>{feature.id}</span>
      <span className="tb-row-header__name">{feature.title}</span>
      <span className="tb-row-header__role">{storyCount} stories · JS {feature.js || 0}</span>
      <span className="tb-row-header__owner">{feature.owner || '-'}</span>
    </div>
  );
}

// -- Main Component -----------------------------------------------------------

export function TeamBoard() {
  const items = useBacklogStore(s => s.items);
  const updateItem = useBacklogStore(s => s.updateItem);
  const saveItem = useBacklogStore(s => s.saveItem);
  const people = useConfigStore(s => s.people);
  const pi = useConfigStore(s => s.currentPI());
  const isReadonly = useConfigStore(s => s.isReadonly);

  const teamIds = useMemo(() => [...new Set(people.map(p => p.team))], [people]);
  const [selectedTeam, setSelectedTeam] = useState(teamIds[0] || '');
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');

  const iterations = pi?.iterations || [];
  const iterationIds = useMemo(() => new Set(iterations.map(it => it.id)), [iterations]);

  // All items for this team in this PI
  const teamItems = useMemo(() => {
    const teamPeople = new Set(people.filter(p => p.team === selectedTeam).map(p => p.id));
    return items.filter(i => {
      // Item belongs to team if owner/assignee is in team, or contributors include team member
      const owner = i.owner || i.assignee || '';
      if (!teamPeople.has(owner)) {
        const hasTeamContributor = i.contributors?.some(c => teamPeople.has(c.person));
        if (!hasTeamContributor) return false;
      }
      // Must be in this PI or unassigned
      if (i.iteration && !iterationIds.has(i.iteration) && !iterations.some(it => i.iteration!.startsWith(it.id))) return false;
      return true;
    });
  }, [items, people, selectedTeam, iterationIds, iterations]);

  // Group stories by parent feature
  const featureGroups = useMemo(() => {
    const features = teamItems.filter(i => i.type === 'Feature');
    const stories = teamItems.filter(i => i.type === 'Story');

    const groups: { feature: WorkItem | null; stories: WorkItem[] }[] = [];

    // Features with their stories
    features.forEach(f => {
      const fStories = stories.filter(s => s.parent === f.id);
      groups.push({ feature: f, stories: fStories });
    });

    // Orphan stories (no parent feature in this team)
    const assignedStoryIds = new Set(groups.flatMap(g => g.stories.map(s => s.id)));
    const orphans = stories.filter(s => !assignedStoryIds.has(s.id));
    if (orphans.length > 0) {
      groups.push({ feature: null, stories: orphans });
    }

    return groups;
  }, [teamItems]);

  const handleDrop = (itemId: string, iteration: string) => {
    if (isReadonly) return;
    updateItem(itemId, { iteration });
    saveItem(itemId);
  };

  const gridCols = iterations.length;

  return (
    <div className="tb-container">
      {/* Header */}
      <div className="tb-header">
        <h2 className="tb-header__title">Team Board</h2>
        <div className="tb-header__controls">
          <select
            value={selectedTeam}
            onChange={e => setSelectedTeam(e.target.value)}
            className="tb-select"
          >
            {teamIds.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <div className="tb-view-toggle">
            <button
              className={`tb-view-btn ${viewMode === 'cards' ? 'tb-view-btn--active' : ''}`}
              onClick={() => setViewMode('cards')}
              title="Card view"
            >▦</button>
            <button
              className={`tb-view-btn ${viewMode === 'table' ? 'tb-view-btn--active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Table view"
            >≡</button>
          </div>
        </div>
      </div>

      {/* Grid: feature groups × iterations */}
      <div className="tb-grid" style={{ gridTemplateColumns: `180px repeat(${gridCols}, 1fr)` }}>
        {/* Corner */}
        <div className="tb-corner">
          <span className="tb-corner__label">Backlog / Iteration</span>
        </div>

        {/* Iteration headers */}
        {iterations.map(iter => (
          <div key={iter.id} className={`tb-col-header ${iter.status === 'active' ? 'tb-col-header--active' : ''}`}>
            <span className="tb-col-header__id">{iter.type ? `${iter.id} (${iter.type})` : iter.id}</span>
            <span className="tb-col-header__dates">{iter.dates}</span>
            <span className={`tb-col-header__status tb-col-header__status--${iter.status}`}>
              {iter.status}
            </span>
          </div>
        ))}

        {/* Feature group rows */}
        {featureGroups.map((group, gIdx) => {
          const allItems = group.feature ? [group.feature, ...group.stories] : group.stories;
          return (
            <Fragment key={group.feature?.id || `orphans-${gIdx}`}>
              <FeatureHeader feature={group.feature} storyCount={group.stories.length} />
              {iterations.map(iter => {
                const cellItems = allItems.filter(i => iterMatch(i, iter));
                return (
                  <IterCell
                    key={`${group.feature?.id || 'orphan'}-${iter.id}`}
                    iterationId={iter.id}
                    items={cellItems}
                    viewMode={viewMode}
                    onDrop={handleDrop}
                    isIP={iter.type === 'IP'}
                  />
                );
              })}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
