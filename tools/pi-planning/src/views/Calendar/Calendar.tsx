import { useMemo } from 'react';
import { useConfigStore } from '../../store/config-store';
import type { PIConfig } from '../../types/edpa';

// -- Date helpers -------------------------------------------------------------

const pad = (n: number) => (n < 10 ? '0' + n : '' + n);
const ds = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;
const daysInMonth = (y: number, m: number) => new Date(y, m, 0).getDate();
const dayOfWeek = (y: number, m: number, d: number) => (new Date(y, m - 1, d).getDay() + 6) % 7;

function parseDate(d: string, fallbackYear?: number): Date {
  if (/^\d{4}-\d{2}-\d{2}/.test(d)) return new Date(d + 'T00:00:00');
  const clean = d.replace(/\s/g, '');
  const parts = clean.split('.').filter(Boolean);
  const day = parseInt(parts[0]);
  const month = parseInt(parts[1]) - 1;
  const year = parts[2] ? parseInt(parts[2]) : (fallbackYear || new Date().getFullYear());
  return new Date(year, month, day);
}

function parseDateRange(dates: string): { start: Date; end: Date } {
  const [s, e] = dates.split('–');
  const endDate = parseDate(e.trim());
  const startDate = parseDate(s.trim(), endDate.getFullYear());
  return { start: startDate, end: endDate };
}

// Year-safe iteration range. Prefer the ISO `start_date`/`end_date` fields
// (which carry the real year) over the pretty `dates` string, whose `D.M.`
// format drops the year and would collapse every PI onto the current year.
function iterRange(iter: { dates: string; start_date?: string; end_date?: string }): { start: Date; end: Date } {
  if (iter.start_date && iter.end_date) {
    return { start: parseDate(iter.start_date), end: parseDate(iter.end_date) };
  }
  return parseDateRange(iter.dates);
}

function dateToStr(d: Date): string {
  return ds(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

function getMonday(y: number, m: number, d: number): string {
  const dt = new Date(y, m - 1, d);
  const dw = (dt.getDay() + 6) % 7;
  const mon = new Date(dt);
  mon.setDate(dt.getDate() - dw);
  return dateToStr(mon);
}

// -- Public holidays (CZ 2026) ------------------------------------------------

const HOLIDAYS: Record<string, string> = {
  '2026-01-01': 'Nový rok',
  '2026-04-03': 'Velký pátek',
  '2026-04-06': 'Velikonoční pondělí',
  '2026-05-01': 'Svátek práce',
  '2026-05-08': 'Den vítězství',
  '2026-07-05': 'Den slovanských věrozvěstů',
  '2026-07-06': 'Den Jana Husa',
  '2026-09-28': 'Den české státnosti',
  '2026-10-28': 'Den vzniku ČSR',
  '2026-11-17': 'Den boje za svobodu',
  '2026-12-24': 'Štědrý den',
  '2026-12-25': '1. svátek vánoční',
  '2026-12-26': '2. svátek vánoční',
};

// -- PI Colors (matching reference) -------------------------------------------

// No green — green is reserved for IP iterations
const PI_PALETTE: { bg: string; text: string; border: string; label: string }[] = [
  { bg: '#dbeafe', text: '#1e3a8a', border: '#93c5fd', label: '#2563eb' },  // blue
  { bg: '#fef3c7', text: '#78350f', border: '#fcd34d', label: '#d97706' },  // amber
  { bg: '#fce7f3', text: '#831843', border: '#f9a8d4', label: '#db2777' },  // pink
  { bg: '#e0e7ff', text: '#312e81', border: '#a5b4fc', label: '#6366f1' },  // indigo
  { bg: '#fecaca', text: '#7f1d1d', border: '#fca5a5', label: '#dc2626' },  // red
  { bg: '#cffafe', text: '#164e63', border: '#67e8f9', label: '#0891b2' },  // cyan
];

const IP_STYLE = { bg: '#bbf7d0', text: '#14532d', border: '#86efac' };

// -- Build day lookup ---------------------------------------------------------

interface DayInfo {
  piIdx: number;
  piId: string;
  iterationId: string;
  iterNum: number;
  isIP: boolean;
}

interface WeekLabel {
  text: string;
  color: string;
  bold: boolean;
}

function buildMaps(pis: PIConfig[]) {
  const dayMap = new Map<string, DayInfo>();
  const weekLabels = new Map<string, WeekLabel>();
  let minDate: Date | null = null;
  let maxDate: Date | null = null;

  pis.forEach((pi, piIdx) => {
    pi.iterations.forEach((iter, iterIdx) => {
      const { start, end } = iterRange(iter);
      if (!minDate || start < minDate) minDate = new Date(start);
      if (!maxDate || end > maxDate) maxDate = new Date(end);

      const cur = new Date(start);
      while (cur <= end) {
        const dow = (cur.getDay() + 6) % 7;
        if (dow < 5) {
          dayMap.set(dateToStr(cur), {
            piIdx, piId: pi.id,
            iterationId: iter.id, iterNum: iterIdx + 1,
            isIP: iter.type === 'IP',
          });
        }
        cur.setDate(cur.getDate() + 1);
      }

      // Week labels for each week of the iteration
      const iterStart = new Date(start);
      while (iterStart <= end) {
        const monKey = getMonday(iterStart.getFullYear(), iterStart.getMonth() + 1, iterStart.getDate());
        if (!weekLabels.has(monKey)) {
          const label = iter.type === 'IP'
            ? `${pi.id} – IP`
            : `${pi.id} – Iterace ${iterIdx + 1}`;
          weekLabels.set(monKey, {
            text: label,
            color: PI_PALETTE[piIdx % PI_PALETTE.length].label,
            bold: iter.type === 'IP',
          });
        }
        iterStart.setDate(iterStart.getDate() + 7);
      }
    });

    // Events as week labels (override iteration labels)
    (pi.events || []).forEach(evt => {
      const evtDate = parseDate(evt.date);
      const monKey = getMonday(evtDate.getFullYear(), evtDate.getMonth() + 1, evtDate.getDate());
      weekLabels.set(monKey, {
        text: `${pi.id} – ${evt.title}`,
        color: PI_PALETTE[piIdx % PI_PALETTE.length].label,
        bold: true,
      });
      if (!minDate || evtDate < minDate) minDate = new Date(evtDate);
      if (!maxDate || evtDate > maxDate) maxDate = new Date(evtDate);
    });
  });

  return { dayMap, weekLabels, minDate, maxDate };
}

// -- Month Component ----------------------------------------------------------

function MonthCal({
  year, month, label, dayMap, weekLabels, todayStr,
}: {
  year: number; month: number; label: string;
  dayMap: Map<string, DayInfo>;
  weekLabels: Map<string, WeekLabel>;
  todayStr: string;
}) {
  const days = daysInMonth(year, month);
  const firstDow = dayOfWeek(year, month, 1);

  const weeks: (number | null)[][] = [];
  let wk: (number | null)[] = new Array(7).fill(null);
  let cur = 1;
  for (let i = firstDow; i < 7 && cur <= days; i++) wk[i] = cur++;
  weeks.push(wk);
  while (cur <= days) {
    wk = new Array(7).fill(null);
    for (let i = 0; i < 7 && cur <= days; i++) wk[i] = cur++;
    weeks.push(wk);
  }

  return (
    <div style={{
      background: '#fff', borderRadius: 8, border: '1px solid #e2e8f0',
      overflow: 'hidden', fontSize: 11,
    }}>
      <div style={{
        background: '#1e293b', color: '#fff', padding: '6px 12px',
        fontWeight: 700, fontSize: 13,
      }}>{label}</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <thead>
          <tr>
            {['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'].map((d, i) => (
              <th key={i} style={{
                padding: '4px 2px', textAlign: 'center', fontSize: 10,
                fontWeight: 500, borderBottom: '1px solid #e2e8f0',
                fontFamily: "'JetBrains Mono', monospace",
                color: i >= 5 ? '#d1d5db' : '#64748b',
                background: i >= 5 ? '#f9fafb' : 'transparent',
                width: i < 5 ? '10.5%' : '7%',
              }}>{d}</th>
            ))}
            <th style={{
              padding: '4px 4px', fontSize: 10, fontWeight: 400, color: '#94a3b8',
              borderBottom: '1px solid #e2e8f0', width: '27%',
            }} />
          </tr>
        </thead>
        <tbody>
          {weeks.map((wkArr, wi) => {
            // Week label
            const firstDay = wkArr.find(d => d !== null);
            const monKey = firstDay ? getMonday(year, month, firstDay) : '';
            const wl = monKey ? weekLabels.get(monKey) : null;

            return (
              <tr key={wi} style={{ borderBottom: '1px solid #f8fafc' }}>
                {wkArr.map((day, di) => {
                  if (day === null) {
                    return <td key={di} style={{ padding: '5px 2px', background: '#f9fafb' }} />;
                  }
                  const dateStr = ds(year, month, day);
                  const isToday = dateStr === todayStr;
                  const isWeekend = di >= 5;
                  const isHoliday = !!HOLIDAYS[dateStr];
                  const info = dayMap.get(dateStr);

                  let bg: string;
                  let textColor: string;
                  let borderBottom = '2px solid transparent';

                  if (isHoliday && !isWeekend) {
                    bg = '#e2e8f0';
                    textColor = '#64748b';
                    borderBottom = '2px solid #cbd5e1';
                  } else if (isWeekend) {
                    bg = '#f9fafb';
                    textColor = '#d1d5db';
                  } else if (info?.isIP) {
                    bg = IP_STYLE.bg;
                    textColor = IP_STYLE.text;
                    borderBottom = `2px solid ${IP_STYLE.border}`;
                  } else if (info) {
                    const palette = PI_PALETTE[info.piIdx % PI_PALETTE.length];
                    bg = palette.bg;
                    textColor = palette.text;
                    borderBottom = `2px solid ${palette.border}`;
                  } else {
                    bg = 'transparent';
                    textColor = '#d1d5db';
                  }

                  // Today: solid accent background
                  if (isToday) {
                    bg = '#6366f1';
                    textColor = '#ffffff';
                    borderBottom = '2px solid #4f46e5';
                  }

                  return (
                    <td key={di} title={HOLIDAYS[dateStr] || ''} style={{
                      padding: '5px 2px', textAlign: 'center', fontWeight: isToday ? 800 : 500,
                      background: bg, color: textColor, borderBottom,
                    }}>{day}</td>
                  );
                })}
                <td style={{
                  padding: '2px 6px', textAlign: 'right', fontSize: 9,
                  lineHeight: '1.15', verticalAlign: 'middle',
                }}>
                  {wl && (
                    <span style={{
                      color: wl.color,
                      fontWeight: wl.bold ? 700 : 400,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}>{wl.text}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// -- Main Component -----------------------------------------------------------

const MONTH_NAMES = [
  '', 'Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
  'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec',
];

export function Calendar() {
  const pis = useConfigStore(s => s.pis);
  const project = useConfigStore(s => s.project);
  const todayStr = dateToStr(new Date());

  const built = useMemo(() => buildMaps(pis), [pis]);
  const { dayMap, weekLabels } = built;
  const minDate = built.minDate as Date | null;
  const maxDate = built.maxDate as Date | null;

  // Generate months — start from beginning of the quarter containing minDate
  const months = useMemo(() => {
    if (!minDate || !maxDate) return [];
    // Start from Q start (Jan/Apr/Jul/Oct)
    const qStart = Math.floor(minDate.getMonth() / 3) * 3;
    const startY = minDate.getFullYear();
    const qEnd = Math.floor(maxDate.getMonth() / 3) * 3 + 2;
    const endY = maxDate.getFullYear();

    const result: { year: number; month: number; label: string }[] = [];
    let y = startY, m = qStart + 1;
    while (y < endY || (y === endY && m <= qEnd + 1)) {
      result.push({ year: y, month: m, label: `${MONTH_NAMES[m]} ${y}` });
      m++;
      if (m > 12) { m = 1; y++; }
    }
    return result;
  }, [minDate, maxDate]);

  // Group months by year, then chunk each year into quarter-columns. A
  // multi-year PI set renders one labeled block per year instead of
  // collapsing every year under a single (wrong) heading.
  const years = useMemo(() => {
    const byYear = new Map<number, { year: number; month: number; label: string }[]>();
    for (const m of months) {
      const arr = byYear.get(m.year) || [];
      arr.push(m);
      byYear.set(m.year, arr);
    }
    return [...byYear.entries()].map(([year, yMonths]) => {
      const quarters: { year: number; month: number; label: string }[][] = [];
      for (let i = 0; i < yMonths.length; i += 3) quarters.push(yMonths.slice(i, i + 3));
      return { year, quarters };
    });
  }, [months]);

  return (
    <div style={{ padding: 16, height: '100%', overflow: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 40, fontWeight: 900, color: '#1e293b', letterSpacing: '-0.02em' }}>
              {(() => {
                const lo = minDate?.getFullYear();
                const hi = maxDate?.getFullYear();
                if (!lo) return 2026;
                return hi && hi !== lo ? `${lo}–${hi}` : lo;
              })()}
            </span>
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#64748b' }}>
            {project?.name || 'EDPA'} — PI Kalendář
          </div>
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginLeft: 'auto', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: '#e2e8f0', border: '1px solid #cbd5e1' }} />
            <span style={{ fontSize: 10, color: '#64748b' }}>Státní svátky</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: IP_STYLE.bg, border: `1px solid ${IP_STYLE.border}` }} />
            <span style={{ fontSize: 10, color: '#64748b' }}>IP iteration</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: '#6366f1' }} />
            <span style={{ fontSize: 10, color: '#64748b' }}>Dnes</span>
          </div>
        </div>
      </div>

      {/* PI badges */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {pis.map((pi, i) => (
          <div key={pi.id} style={{
            padding: '4px 14px', borderRadius: 20, fontSize: 12, fontWeight: 700,
            fontFamily: "'JetBrains Mono', monospace",
            background: PI_PALETTE[i % PI_PALETTE.length].label,
            color: '#fff',
          }}>
            {pi.id} ({pi.pi_iterations})
          </div>
        ))}
      </div>

      {/* One labeled block per year; within a year, quarters as columns */}
      {years.map(({ year, quarters }) => (
        <div key={year} style={{ marginBottom: 28 }}>
          {years.length > 1 && (
            <div style={{
              fontSize: 22, fontWeight: 800, color: '#1e293b',
              letterSpacing: '-0.01em', marginBottom: 12,
              paddingBottom: 6, borderBottom: '2px solid #e2e8f0',
            }}>{year}</div>
          )}
          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${quarters.length}, 1fr)`,
            gap: 16,
            alignItems: 'start',
          }}>
            {quarters.map((q, qi) => (
              <div key={qi} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {q.map(m => (
                  <MonthCal
                    key={`${m.year}-${m.month}`}
                    year={m.year}
                    month={m.month}
                    label={m.label}
                    dayMap={dayMap}
                    weekLabels={weekLabels}
                    todayStr={todayStr}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
