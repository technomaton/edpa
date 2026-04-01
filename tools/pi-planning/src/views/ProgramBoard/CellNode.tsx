import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';

function CellNodeInner({ data }: NodeProps) {
  const { teamId, iterationId, used, available, isActive, isDropTarget } = data as {
    teamId: string;
    iterationId: string;
    used: number;
    available: number;
    isActive: boolean;
    isDropTarget: boolean;
  };

  const pct = available > 0 ? Math.min(100, (used / available) * 100) : 0;
  const over = used > available && available > 0;

  return (
    <div className={`rf-cell ${isActive ? 'rf-cell--active' : ''} ${isDropTarget ? 'rf-cell--drop-target' : ''}`}>
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
