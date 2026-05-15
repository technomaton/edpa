import { memo } from 'react';
import type { NodeProps } from '@xyflow/react';

function HeaderNodeInner({ data }: NodeProps) {
  const { label, sublabel, badge, variant, status } = data as {
    label: string;
    sublabel?: string;
    badge?: string;
    variant: 'column' | 'row' | 'corner' | 'events-row' | 'external-row';
    status?: string;
  };

  return (
    <div className={`rf-header rf-header--${variant}`}>
      <span className="rf-header__label">{label}</span>
      {sublabel && <span className="rf-header__sub">{sublabel}</span>}
      {(status || badge) && (
        <div className="rf-header__tags">
          {status && (
            <span className={`rf-header__status rf-header__status--${status}`}>
              {status}
            </span>
          )}
          {badge && <span className="rf-header__badge">{badge}</span>}
        </div>
      )}
    </div>
  );
}

export const HeaderNode = memo(HeaderNodeInner);
