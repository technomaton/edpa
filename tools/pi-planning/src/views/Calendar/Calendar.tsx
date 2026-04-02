import { useMemo } from 'react';
import { useConfigStore } from '../../store/config-store';
import type { PIConfig, PIEvent } from '../../types/edpa';

// -- Date helpers -------------------------------------------------------------

const pad = (n: number) => (n < 10 ? '0' + n : '' + n);
const ds = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`;
const daysInMonth = (y: number, m: number) => new Date(y, m, 0).getDate();
const dayOfWeek = (y: number, m: number, d: number) => (new Date(y, m - 1, d).getDay() + 6) % 7; // 0=Mon

function parseDate(d: string, fallbackYear?: number): Date {
  if (/^\d{4}-\d{2}-\d{2}/.test(d)) return new Date(d);
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

function dateToStr(d: Date): string {
  return ds(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

// -- PI Colors ----------------------------------------------------------------

const PI_COLORS = [
  '#6366f1', '#2563eb', '#059669', '#d97706', '#dc2626',
  '#7c3aed', '#0891b2', '#65a30d', '#c2410c', '#be185d',
];

const IP_STYLES = {
  ip: { bg: '#bbf7d0', text: '#14532d', border: '#86efac' },
};

const CELL_STYLES = {
  weekend: { bg: '#f9fafb', text: '#d1d5db' },
  today: { bg: '#1e40af', text: '#ffffff' },
  empty: { bg: 'transparent', text: '#d1d5db' },
};

// -- Build date map from PI config --------------------------------------------

interface DayInfo {
  piId: string;
  piColor: string;
  iterationId: string;
  isIP: boolean;
  iterNum: number;
}

interface EventInfo {
  title: string;
  type: string;
  piId: string;
  piColor: string;
}

function buildDateMaps(pis: PIConfig[]) {
  const dayMap = new Map<string, DayInfo>();
  const eventMap = new Map<string, EventInfo[]>();
  let minDate: Date | null = null;
  let maxDate: Date | null = null;

  pis.forEach((pi, piIdx) => {
    const color = PI_COLORS[piIdx % PI_COLORS.length];

    pi.iterations.forEach((iter, iterIdx) => {
      const { start, end } = parseDateRange(iter.dates);
      if (!minDate || start < minDate) minDate = start;
      if (!maxDate || end > maxDate) maxDate = end;

      // Fill every day in the iteration
      const cur = new Date(start);
      while (cur <= end) {
        const key = dateToStr(cur);
        const dow = (cur.getDay() + 6) % 7;
        if (dow < 5) { // weekdays only
          dayMap.set(key, {
            piId: pi.id,
            piColor: color,
            iterationId: iter.id,
            isIP: iter.type === 'IP',
            iterNum: iterIdx + 1,
          });
        }
        cur.setDate(cur.getDate() + 1);
      }
    });

    // Events
    (pi.events || []).forEach(evt => {
      const key = evt.date;
      const list = eventMap.get(key) || [];
      list.push({ title: evt.title, type: evt.type, piId: pi.id, piColor: color });
      eventMap.set(key, list);
    });
  });

  return { dayMap, eventMap, minDate, maxDate };
}

// -- Week label: find events in this week -------------------------------------

function getWeekEvents(
  year: number, month: number, weekDays: (number | null)[],
  eventMap: Map<string, EventInfo[]>,
  dayMap: Map<string, DayInfo>,
): { label: string; color: string } | null {
  for (const day of weekDays) {
    if (day === null) continue;
    const key = ds(year, month, day);
    const evts = eventMap.get(key);
    if (evts && evts.length > 0) {
      return { label: evts.map(e => e.title).join(' / '), color: evts[0].piColor };
    }
  }
  // If no event, show iteration label for the week
  for (const day of weekDays) {
    if (day === null) continue;
    const key = ds(year, month, day);
    const info = dayMap.get(key);
    if (info) {
      const label = info.isIP ? `${info.piId} – IP` : `${info.piId} – Iter ${info.iterNum}`;
      return { label, color: info.piColor + '80' };
    }
  }
  return null;
}

// -- Month Component ----------------------------------------------------------

function MonthCal({
  year, month, label, dayMap, eventMap, todayStr,
}: {
  year: number; month: number; label: string;
  dayMap: Map<string, DayInfo>;
  eventMap: Map<string, EventInfo[]>;
  todayStr: string;
}) {
  const days = daysInMonth(year, month);
  const firstDow = dayOfWeek(year, month, 1);

  // Build weeks
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
                padding: '4px 2px', textAlign: 'center', fontSize: 10, fontWeight: 500,
                borderBottom: '1px solid #e2e8f0', fontFamily: "'JetBrains Mono', monospace",
                color: i >= 5 ? '#d1d5db' : '#64748b', background: i >= 5 ? '#f9fafb' : 'transparent',
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
            const weekEvt = getWeekEvents(year, month, wkArr, eventMap, dayMap);
            return (
              <tr key={wi} style={{ borderBottom: '1px solid #f8fafc' }}>
                {wkArr.map((day, di) => {
                  if (day === null) {
                    return <td key={di} style={{ padding: '5px 2px', background: '#f9fafb' }} />;
                  }
                  const dateStr = ds(year, month, day);
                  const isToday = dateStr === todayStr;
                  const isWeekend = di >= 5;
                  const info = dayMap.get(dateStr);

                  let bg = 'transparent';
                  let textColor = '#374151';
                  let borderBottom = '2px solid transparent';

                  if (isToday) {
                    bg = '#1e40af';
                    textColor = '#ffffff';
                    borderBottom = '2px solid #1e40af';
                  } else if (isWeekend) {
                    bg = '#f9fafb';
                    textColor = '#d1d5db';
                  } else if (info) {
                    if (info.isIP) {
                      bg = IP_STYLES.ip.bg;
                      textColor = IP_STYLES.ip.text;
                      borderBottom = `2px solid ${IP_STYLES.ip.border}`;
                    } else {
                      bg = 'transparent';
                      textColor = '#374151';
                      borderBottom = `2px solid ${info.piColor}`;
                    }
                  }

                  return (
                    <td key={di} style={{
                      padding: '5px 2px', textAlign: 'center', fontWeight: 500,
                      background: bg, color: textColor, borderBottom,
                    }}>
                      {day}
                    </td>
                  );
                })}
                <td style={{
                  padding: '2px 6px', textAlign: 'right', fontSize: 9, lineHeight: '1.15',
                }}>
                  {weekEvt && (
                    <span style={{
                      color: weekEvt.color,
                      fontWeight: weekEvt.label.includes('IP') || weekEvt.label.includes('Demo') || weekEvt.label.includes('Adapt') || weekEvt.label.includes('Planning') ? 700 : 400,
                      fontFamily: "'JetBrains Mono', monospace",
                    }}>
                      {weekEvt.label}
                    </span>
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

  const built = useMemo(() => buildDateMaps(pis), [pis]);
  const { dayMap, eventMap } = built;
  const minDate = built.minDate as Date | null;
  const maxDate = built.maxDate as Date | null;

  // Generate months to display
  const months = useMemo(() => {
    if (!minDate || !maxDate) return [];
    const result: { year: number; month: number; label: string }[] = [];
    const cur = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    const end = new Date(maxDate.getFullYear(), maxDate.getMonth() + 1, 1);
    while (cur < end) {
      const y = cur.getFullYear();
      const m = cur.getMonth() + 1;
      result.push({ year: y, month: m, label: `${MONTH_NAMES[m]} ${y}` });
      cur.setMonth(cur.getMonth() + 1);
    }
    return result;
  }, [minDate, maxDate]);

  return (
    <div style={{ padding: 16, height: '100%', overflow: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 40, fontWeight: 900, color: '#1e293b', letterSpacing: '-0.02em' }}>
              {minDate?.getFullYear() || 2026}
            </span>
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#64748b' }}>
            {project?.name || 'EDPA'} — PI Kalendář
          </div>
        </div>

        {/* Legend */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginLeft: 'auto', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 14, height: 14, borderRadius: 3, background: IP_STYLES.ip.bg, border: `1px solid ${IP_STYLES.ip.border}` }} />
            <span style={{ fontSize: 10, color: '#64748b' }}>IP iteration</span>
          </div>
          {pis.map((pi, i) => (
            <div key={pi.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 14, height: 14, borderRadius: 3,
                borderBottom: `3px solid ${PI_COLORS[i % PI_COLORS.length]}`,
                background: '#fff', border: '1px solid #e2e8f0',
              }} />
              <span style={{ fontSize: 10, color: '#64748b' }}>
                {pi.id} ({pi.pi_iterations})
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* PI badges */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {pis.map((pi, i) => (
          <div key={pi.id} style={{
            padding: '4px 14px', borderRadius: 20, fontSize: 12, fontWeight: 700,
            fontFamily: "'JetBrains Mono', monospace",
            background: PI_COLORS[i % PI_COLORS.length],
            color: '#fff',
          }}>
            {pi.id} ({pi.pi_iterations})
          </div>
        ))}
      </div>

      {/* Monthly grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 16,
      }}>
        {months.map(m => (
          <MonthCal
            key={`${m.year}-${m.month}`}
            year={m.year}
            month={m.month}
            label={m.label}
            dayMap={dayMap}
            eventMap={eventMap}
            todayStr={todayStr}
          />
        ))}
      </div>
    </div>
  );
}
