import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';

function CellNodeInner({ data }: NodeProps) {
  const { used, available, isActive, dropHalf } = data as {
    teamId: string;
    iterationId: string;
    used: number;
    available: number;
    isActive: boolean;
    dropHalf: 0 | 1 | 2; // 0 = none, 1 = W1 highlighted, 2 = W2 highlighted
  };

  const pct = available > 0 ? Math.min(100, (used / available) * 100) : 0;
  const over = used > available && available > 0;

  return (
    <div className={`rf-cell ${isActive ? 'rf-cell--active' : ''}`}>
      {/* W1/W2 halves */}
      <div className={`rf-cell__half rf-cell__half--w1 ${dropHalf === 1 ? 'rf-cell__half--drop' : ''}`}>
        <span className="rf-cell__half-label">W1</span>
      </div>
      <div className="rf-cell__divider" />
      <div className={`rf-cell__half rf-cell__half--w2 ${dropHalf === 2 ? 'rf-cell__half--drop' : ''}`}>
        <span className="rf-cell__half-label">W2</span>
      </div>
      {/* Capacity bar */}
      {available > 0 && (
        <div className="rf-cell__cap">
          <div className="rf-cell__cap-bar">
            <div
              className={`rf-cell__cap-fill ${over ? 'rf-cell__cap-fill--over' : ''}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className={`rf-cell__cap-label ${over ? 'rf-cell__cap-label--over' : ''}`}>
            {used}/{available}
          </span>
        </div>
      )}
    </div>
  );
}

export const CellNode = memo(CellNodeInner);
