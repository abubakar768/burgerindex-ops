'use client';

import type { ReactNode } from 'react';
import s from './ui.module.css';

export function PageHeader({
  eyebrow, title, subtitle, pills, actions, back,
}: {
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  pills?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
}) {
  return (
    <div className={s.phead}>
      <div className={s.pheadLeft}>
        {back}
        <div className={s.eyebrow}>{eyebrow}</div>
        {pills ? (
          <div className={s.titleRow}>
            <h1 className={s.title}>{title}</h1>
            {pills}
          </div>
        ) : (
          <h1 className={s.title}>{title}</h1>
        )}
        {subtitle ? <div className={s.sub}>{subtitle}</div> : null}
      </div>
      {actions ? <div className={s.pheadRight}>{actions}</div> : null}
    </div>
  );
}
