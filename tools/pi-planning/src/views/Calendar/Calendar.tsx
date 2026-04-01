import { useMemo } from 'react';
import { useConfigStore } from '../../store/config-store';
import type { PIConfig, PIEvent } from '../../types/edpa';

// -- Helpers ------------------------------------------------------------------

function parseDate(d: string): Date {
  // Handle both ISO (2026-04-28) and Czech (28.4.2026) formats
  if (d.includes('-')) return new Date(d);
  const parts = d.split('.');
  return new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
}

function parseDateRange(dates: string): { start: Date; end: Date } {
  const [s, e] = dates.split('–');
  return { start: parseDate(s.trim()), end: parseDate(e.trim()) };
}

function formatMonth(d: Date): string {
  return d.toLocaleDateString('en', { month: 'short' });
}

function formatDay(d: Date): string {
  return d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
}

function weeksBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / (7 * 24 * 60 * 60 * 1000));
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

const EVENT_COLORS: Record<string, { bg: string; fg: string; border: string }> = {
  pi_planning:   { bg: 'rgba(99,102,241,0.12)', fg: '#6366f1', border: '#6366f1' },
  system_demo:   { bg: 'rgba(8,145,178,0.12)',  fg: '#0891b2', border: '#0891b2' },
  inspect_adapt: { bg: 'rgba(245,158,11,0.12)', fg: '#d97706', border: '#f59e0b' },
  prioritization:{ bg: 'rgba(219,39,119,0.12)', fg: '#db2777', border: '#db2777' },
  custom:        { bg: 'rgba(99,102,241,0.08)', fg: '#6366f1', border: '#6366f1' },
};

const PI_STATUS_COLORS: Record<string, string> = {
  active: '#6366f1',
  planning: '#d97706',
  closed: '#059669',
};

// -- PI Block -----------------------------------------------------------------

function PIBlock({ pi, yearStart, weekWidth }: { pi: PIConfig; yearStart: Date; weekWidth: number }) {
  const iters = pi.iterations;
  if (iters.length === 0) return null;

  const firstIter = parseDateRange(iters[0].dates);
  const lastIter = parseDateRange(iters[iters.length - 1].dates);
  const startWeek = weeksBetween(yearStart, firstIter.start);
  const endWeek = weeksBetween(yearStart, lastIter.end);
  const left = startWeek * weekWidth;
  const width = (endWeek - startWeek) * weekWidth;
  const statusColor = PI_STATUS_COLORS[pi.status] || '#8892a8';

  return (
    <div className="cal-pi" style={{ left, width }}>
      {/* PI bar */}
      <div className="cal-pi__bar" style={{ borderColor: statusColor, background: `${statusColor}08` }}>
        <span className="cal-pi__label" style={{ color: statusColor }}>{pi.id}</span>
        <span className="cal-pi__status" style={{ color: statusColor }}>{pi.status}</span>
      </div>

      {/* Iteration blocks */}
      <div className="cal-pi__iters">
        {iters.map(iter => {
          const { start, end } = parseDateRange(iter.dates);
          const iterLeft = weeksBetween(yearStart, start) * weekWidth - left;
          const iterWidth = weeksBetween(yearStart, end) * weekWidth - iterLeft - left;
          const isIP = iter.type === 'IP';
          const statusCls = iter.status === 'active' ? 'cal-iter--active'
            : iter.status === 'closed' ? 'cal-iter--closed' : '';

          return (
            <div
              key={iter.id}
              className={`cal-iter ${statusCls} ${isIP ? 'cal-iter--ip' : ''}`}
              style={{
                left: iterLeft,
                width: Math.max(iterWidth, weekWidth),
              }}
            >
              <span className="cal-iter__id">{iter.id.split('.').pop()}</span>
              <span className="cal-iter__dates">{iter.dates}</span>
            </div>
          );
        })}
      </div>

      {/* Events */}
      <div className="cal-pi__events">
        {(pi.events || []).map((evt, i) => {
          const evtDate = parseDate(evt.date);
          const evtLeft = weeksBetween(yearStart, evtDate) * weekWidth - left;
          const colors = EVENT_COLORS[evt.type] || EVENT_COLORS.custom;
          return (
            <div
              key={`${evt.type}-${i}`}
              className="cal-event"
              style={{ left: evtLeft, borderColor: colors.border, background: colors.bg }}
            >
              <span className="cal-event__dot" style={{ background: colors.fg }} />
              <span className="cal-event__title" style={{ color: colors.fg }}>{evt.title}</span>
              <span className="cal-event__date">{formatDay(evtDate)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// -- Main Component -----------------------------------------------------------

export function Calendar() {
  const pis = useConfigStore(s => s.pis);
  const project = useConfigStore(s => s.project);

  // Determine year range from all PIs
  const { yearStart, totalWeeks, months } = useMemo(() => {
    let minDate = new Date();
    let maxDate = new Date();

    pis.forEach(pi => {
      pi.iterations.forEach(iter => {
        const { start, end } = parseDateRange(iter.dates);
        if (start < minDate) minDate = start;
        if (end > maxDate) maxDate = end;
      });
      (pi.events || []).forEach(evt => {
        const d = parseDate(evt.date);
        if (d < minDate) minDate = d;
        if (d > maxDate) maxDate = d;
      });
    });

    // Extend to full months
    const ys = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    const ye = new Date(maxDate.getFullYear(), maxDate.getMonth() + 2, 0);
    const tw = weeksBetween(ys, ye);

    // Generate month markers
    const ms: { label: string; offset: number }[] = [];
    const cur = new Date(ys);
    while (cur <= ye) {
      ms.push({ label: `${formatMonth(cur)} ${cur.getFullYear()}`, offset: weeksBetween(ys, cur) });
      cur.setMonth(cur.getMonth() + 1);
    }

    return { yearStart: ys, totalWeeks: tw, months: ms };
  }, [pis]);

  const WEEK_W = 40;
  const totalWidth = totalWeeks * WEEK_W;

  return (
    <div className="cal-container">
      <div className="cal-header">
        <h2 className="cal-header__title">Calendar</h2>
        {project && <span className="cal-header__project">{project.name}</span>}
      </div>

      <div className="cal-scroll">
        <div className="cal-timeline" style={{ width: totalWidth }}>
          {/* Month headers */}
          <div className="cal-months">
            {months.map((m, i) => {
              const nextOffset = months[i + 1]?.offset ?? totalWeeks;
              const w = (nextOffset - m.offset) * WEEK_W;
              return (
                <div key={m.label} className="cal-month" style={{ left: m.offset * WEEK_W, width: w }}>
                  {m.label}
                </div>
              );
            })}
          </div>

          {/* Week grid lines */}
          <div className="cal-weeks">
            {Array.from({ length: totalWeeks }, (_, i) => (
              <div key={i} className="cal-week-line" style={{ left: i * WEEK_W }} />
            ))}
          </div>

          {/* Today marker */}
          {(() => {
            const todayWeek = weeksBetween(yearStart, new Date());
            if (todayWeek >= 0 && todayWeek <= totalWeeks) {
              return <div className="cal-today" style={{ left: todayWeek * WEEK_W }} />;
            }
            return null;
          })()}

          {/* PI blocks */}
          <div className="cal-pis">
            {pis.map(pi => (
              <PIBlock key={pi.id} pi={pi} yearStart={yearStart} weekWidth={WEEK_W} />
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="cal-legend">
        {Object.entries(EVENT_COLORS).map(([type, colors]) => (
          <div key={type} className="cal-legend__item">
            <span className="cal-legend__dot" style={{ background: colors.fg }} />
            <span className="cal-legend__label">{type.replace('_', ' ')}</span>
          </div>
        ))}
        <div className="cal-legend__item">
          <span className="cal-legend__dot" style={{ background: '#6366f1' }} />
          <span className="cal-legend__label">active</span>
        </div>
        <div className="cal-legend__item">
          <span className="cal-legend__dot" style={{ background: '#d97706' }} />
          <span className="cal-legend__label">planning</span>
        </div>
        <div className="cal-legend__item">
          <span className="cal-legend__dot" style={{ background: '#059669' }} />
          <span className="cal-legend__label">closed</span>
        </div>
      </div>
    </div>
  );
}
