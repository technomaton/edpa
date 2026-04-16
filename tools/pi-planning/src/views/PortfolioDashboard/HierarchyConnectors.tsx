interface CardPosition {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  band: string;
}

interface Props {
  positions: CardPosition[];
  pairs: { parentId: string; childId: string }[];
}

const BAND_COLORS: Record<string, string> = {
  enterprise: '#db2777',
  portfolio: '#6366f1',
  program: '#059669',
  team: '#ea580c',
};

export function HierarchyConnectors({ positions, pairs }: Props) {
  if (positions.length === 0 || pairs.length === 0) return null;

  const posMap = new Map(positions.map(p => [p.id, p]));

  const lines = pairs
    .map(({ parentId, childId }) => {
      const parent = posMap.get(parentId);
      const child = posMap.get(childId);
      if (!parent || !child) return null;
      return { parent, child, key: `${parentId}-${childId}` };
    })
    .filter(Boolean) as { parent: CardPosition; child: CardPosition; key: string }[];

  if (lines.length === 0) return null;

  return (
    <svg className="hierarchy-connectors" style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'visible' }}>
      <defs>
        {Object.entries(BAND_COLORS).map(([band, color]) => (
          <linearGradient key={band} id={`grad-${band}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.6} />
            <stop offset="100%" stopColor={color} stopOpacity={0.2} />
          </linearGradient>
        ))}
      </defs>
      {lines.map(({ parent, child, key }) => {
        const x1 = parent.x;
        const y1 = parent.y + parent.height / 2;
        const x2 = child.x;
        const y2 = child.y - child.height / 2;
        const cy1 = y1 + (y2 - y1) * 0.4;
        const cy2 = y1 + (y2 - y1) * 0.6;
        const grad = `url(#grad-${parent.band})`;

        return (
          <path
            key={key}
            d={`M${x1},${y1} C${x1},${cy1} ${x2},${cy2} ${x2},${y2}`}
            fill="none"
            stroke={grad}
            strokeWidth={1.5}
            opacity={0.5}
          />
        );
      })}
    </svg>
  );
}
