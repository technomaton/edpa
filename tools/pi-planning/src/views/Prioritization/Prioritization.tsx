import { useMemo, useState } from 'react';
import { useBacklogStore } from '../../store/backlog-store';
import { useConfigStore } from '../../store/config-store';

type SortKey = 'wsjf' | 'bv' | 'tc' | 'rr' | 'js' | 'title';

export function Prioritization() {
  const items = useBacklogStore(s => s.items);
  const pi = useConfigStore(s => s.currentPI());
  const [sortBy, setSortBy] = useState<SortKey>('wsjf');
  const [sortAsc, setSortAsc] = useState(false);
  const [filterType, setFilterType] = useState<string>('Feature');

  const features = useMemo(() => {
    const iterationIds = new Set(pi?.iterations.map(it => it.id) || []);
    const piItems = items.filter(i => {
      if (!i.iteration) return true; // unassigned items still show
      return iterationIds.has(i.iteration) || (pi?.iterations || []).some(it => i.iteration!.startsWith(it.id));
    });
    const filtered = piItems.filter(i =>
      filterType ? i.type === filterType : true,
    );
    return [...filtered].sort((a, b) => {
      const aVal = a[sortBy] ?? 0;
      const bVal = b[sortBy] ?? 0;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortAsc ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });
  }, [items, pi, sortBy, sortAsc, filterType]);

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) setSortAsc(!sortAsc);
    else { setSortBy(key); setSortAsc(false); }
  };

  const sortIcon = (key: SortKey) =>
    sortBy === key ? (sortAsc ? ' ▲' : ' ▼') : '';

  return (
    <div className="prioritization">
      <div className="prio-header">
        <h2 className="prio-header__title">WSJF Prioritization</h2>
        <select
          className="tb-select"
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
        >
          <option value="Feature">Features</option>
          <option value="Epic">Epics</option>
          <option value="Story">Stories</option>
        </select>
      </div>
      <div className="prio-table-wrap">
        <table className="prio-table">
          <thead>
            <tr>
              <th className="prio-th prio-th--rank">#</th>
              <th className="prio-th prio-th--id">ID</th>
              <th className="prio-th prio-th--title" onClick={() => toggleSort('title')}>
                Title{sortIcon('title')}
              </th>
              <th className="prio-th prio-th--num" onClick={() => toggleSort('bv')}>
                BV{sortIcon('bv')}
              </th>
              <th className="prio-th prio-th--num" onClick={() => toggleSort('tc')}>
                TC{sortIcon('tc')}
              </th>
              <th className="prio-th prio-th--num" onClick={() => toggleSort('rr')}>
                RR{sortIcon('rr')}
              </th>
              <th className="prio-th prio-th--num prio-th--cod">CoD</th>
              <th className="prio-th prio-th--num" onClick={() => toggleSort('js')}>
                JS{sortIcon('js')}
              </th>
              <th className="prio-th prio-th--num prio-th--wsjf" onClick={() => toggleSort('wsjf')}>
                WSJF{sortIcon('wsjf')}
              </th>
              <th className="prio-th">Status</th>
              <th className="prio-th">Iteration</th>
              <th className="prio-th">Owner</th>
            </tr>
          </thead>
          <tbody>
            {features.map((item, idx) => {
              const cod = (item.bv || 0) + (item.tc || 0) + (item.rr || 0);
              return (
                <tr key={item.id} className={`prio-row ${item.status === 'Done' ? 'prio-row--done' : ''}`}>
                  <td className="prio-td prio-td--rank">{idx + 1}</td>
                  <td className="prio-td prio-td--id">{item.id}</td>
                  <td className="prio-td prio-td--title">{item.title}</td>
                  <td className="prio-td prio-td--num prio-td--bv">{item.bv ?? '-'}</td>
                  <td className="prio-td prio-td--num prio-td--tc">{item.tc ?? '-'}</td>
                  <td className="prio-td prio-td--num prio-td--rr">{item.rr ?? '-'}</td>
                  <td className="prio-td prio-td--num prio-td--cod">{cod || '-'}</td>
                  <td className="prio-td prio-td--num prio-td--js">{item.js ?? '-'}</td>
                  <td className="prio-td prio-td--num prio-td--wsjf">
                    {item.wsjf?.toFixed(2) ?? '-'}
                  </td>
                  <td className="prio-td">{item.status}</td>
                  <td className="prio-td">{item.iteration || '-'}</td>
                  <td className="prio-td">{item.owner || item.assignee || '-'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
