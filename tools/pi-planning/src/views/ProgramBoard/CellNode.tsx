import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';

function CellNodeInner({ data }: NodeProps) {
  const { used, available, isActive, isIP, isSingleWeek, dropHalf, dropBlocked } = data as {
    teamId: string;
    iterationId: string;
    used: number;
    available: number;
    isActive: boolean;
    isIP: boolean;
    isSingleWeek: boolean;
    dropHalf: 0 | 1 | 2;
    dropBlocked: boolean;
  };

  const pct = available > 0 ? Math.min(100, (used / available) * 100) : 0;
  const over = used > available && available > 0;

  return (
    <div className={`rf-cell ${isActive ? 'rf-cell--active' : ''} ${isIP ? 'rf-cell--ip' : ''} ${dropBlocked ? 'rf-cell--blocked' : ''} ${isSingleWeek ? 'rf-cell--single' : ''}`}>
      {isSingleWeek ? (
        /* Single week — one column with W1 label */
        <div className={`rf-cell__half rf-cell__half--full ${dropHalf === 1 ? 'rf-cell__half--drop' : ''}`}>
          <span className="rf-cell__half-label">W1</span>
        </div>
      ) : (
        /* Two halves — W1/W2 split */
        <>
          <div className={`rf-cell__half rf-cell__half--w1 ${dropHalf === 1 ? 'rf-cell__half--drop' : ''}`}>
            <span className="rf-cell__half-label">W1</span>
          </div>
          <div className="rf-cell__divider" />
          <div className={`rf-cell__half rf-cell__half--w2 ${dropHalf === 2 ? 'rf-cell__half--drop' : ''}`}>
            <span className="rf-cell__half-label">W2</span>
          </div>
        </>
      )}
      {/* Blocked overlay */}
      {dropBlocked && (
        <div className="rf-cell__blocked-msg">IP — no work items</div>
      )}
      {/* IP label */}
      {isIP && !dropBlocked && (
        <div className="rf-cell__ip-label">Innovation & Planning</div>
      )}
      {/* Capacity bar */}
      {available > 0 && !isIP && (
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
