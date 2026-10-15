'use client';

import type { ReactNode } from 'react';
import { cx, Skeleton } from './Primitives';
import s from './ui.module.css';

/** Scrolling frame. `minWidth` keeps the grid from collapsing on narrow screens. */
export function Table({ minWidth, children }: { minWidth: number; children: ReactNode }) {
  return (
    <div className={s.table}>
      <div style={{ minWidth }}>{children}</div>
    </div>
  );
}

export function HeaderRow({ cols, labels }: { cols: string; labels: string[] }) {
  return (
    <div className={s.th} style={{ gridTemplateColumns: cols }}>
      {labels.map((label) => <div key={label}>{label}</div>)}
    </div>
  );
}

export function Row({
  cols, children,
}: { cols: string; children: ReactNode }) {
  return (
    <div className={s.tr} style={{ gridTemplateColumns: cols }}>
      {children}
    </div>
  );
}

export function SelectableRow({
  cols, selected, onSelect, label, children,
}: {
  cols: string;
  selected: boolean;
  onSelect: () => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={s.tr}
      style={{ gridTemplateColumns: cols }}
      aria-pressed={selected}
      aria-label={label}
      onClick={onSelect}
    >
      {children}
    </button>
  );
}

export function TableFoot({ children }: { children: ReactNode }) {
  return <div className={s.tfoot}>{children}</div>;
}

export function SkeletonRows({ cols, count }: { cols: string; count: number }) {
  const columns = cols.split(' ').length;
  return (
    <>
      {Array.from({ length: count }, (_, rowIndex) => (
        <div key={rowIndex} className={s.tr} style={{ gridTemplateColumns: cols }}>
          {Array.from({ length: columns }, (_, colIndex) => <Skeleton key={colIndex} />)}
        </div>
      ))}
    </>
  );
}

export function CellStack({ children }: { children: ReactNode }) {
  return <span className={s.cellStack}>{children}</span>;
}

export function CellTags({ children }: { children: ReactNode }) {
  return <span className={s.cellTags}>{children}</span>;
}

export const cell = {
  name: s.cellName,
  sub: s.cellSub,
  mono: s.cellMono,
  ink2: s.cellInk2,
};

export { cx };
