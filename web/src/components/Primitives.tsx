'use client';

import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import Link from 'next/link';
import s from './ui.module.css';

export const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ');

/* ----------------------------------------------------------------- icons -- */

const ICON_PATHS = {
  warnTriangle: ['M12 3l9 16H3l9-16z', 'M12 10v4', 'M12 17h.01'],
  shieldCheck: ['M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z', 'M9 12l2 2 4-4'],
  check: ['M5 12l5 5 9-10'],
  cross: ['M6 6l12 12', 'M18 6L6 18'],
  spinner: ['M12 3a9 9 0 1 0 9 9'],
  sun: [
    'M12 4V2', 'M12 22v-2', 'M4 12H2', 'M22 12h-2',
    'M6.3 6.3L4.9 4.9', 'M19.1 19.1l-1.4-1.4',
    'M17.7 6.3l1.4-1.4', 'M4.9 19.1l1.4-1.4',
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  ],
  moon: ['M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z'],
  activity: ['M3 12h4l3 8 4-16 3 8h4'],
  calendar: [
    'M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z',
    'M4 9h16', 'M8 3v4', 'M16 3v4',
  ],
} as const;

export type IconName = keyof typeof ICON_PATHS;

export function Icon({
  name, size = 20, stroke = 'currentColor', width = 2, label,
}: {
  name: IconName; size?: number; stroke?: string; width?: number; label?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={stroke}
      strokeWidth={width}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {ICON_PATHS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

/* --------------------------------------------------------------- buttons -- */

type ButtonTone = 'default' | 'on' | 'solid' | 'primary' | 'ghost' | 'warn' | 'warnSolid' | 'danger';
type ButtonSize = 'default' | 'sm' | 'lg' | 'xl';

const TONE: Record<ButtonTone, string> = {
  default: '', on: s.on, solid: s.solid, primary: s.primary,
  ghost: s.ghost, warn: s.warn, warnSolid: s.warnSolid, danger: s.danger,
};
const SIZE: Record<ButtonSize, string> = { default: '', sm: s.sm, lg: s.lg, xl: s.xl };

export function Button({
  children, tone = 'default', size = 'default', grow, block, flex1,
  onClick, disabled, pressed, type = 'button', title, style,
}: {
  children: ReactNode;
  tone?: ButtonTone;
  size?: ButtonSize;
  grow?: boolean;
  block?: boolean;
  flex1?: boolean;
  onClick?: () => void;
  disabled?: boolean;
  pressed?: boolean;
  type?: 'button' | 'submit';
  title?: string;
  style?: CSSProperties;
}) {
  return (
    <button
      type={type}
      className={cx(s.btn, TONE[tone], SIZE[size], grow && s.grow, block && s.block, flex1 && s.flex1)}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed === undefined ? undefined : pressed}
      title={title}
      style={style}
    >
      {children}
    </button>
  );
}

export function NavButton({
  href, children, tone = 'solid', size = 'default',
}: {
  href: string; children: ReactNode; tone?: ButtonTone; size?: ButtonSize;
}) {
  return (
    <Link href={href} className={cx(s.btn, TONE[tone], SIZE[size])}>
      {children}
    </Link>
  );
}

export function FilterButton({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <Button tone={active ? 'on' : 'default'} pressed={active} onClick={onClick}>
      {label}
    </Button>
  );
}

/* ------------------------------------------------------------------ pills -- */

export function Pill({
  children, tone = 'default',
}: { children: ReactNode; tone?: 'default' | 'dashed' | 'accent' | 'warn' | 'ok' }) {
  const map = {
    default: '', dashed: s.pillDashed, accent: s.pillAccent, warn: s.pillWarn, ok: s.pillOk,
  };
  return <span className={cx(s.pill, map[tone])}>{children}</span>;
}

export function Tag({ children, variant }: { children: ReactNode; variant?: string }) {
  const map: Record<string, string> = {
    srcScheduler: s.srcScheduler,
    srcDashboard: s.srcDashboard,
    srcManual: s.srcManual,
    envStaging: s.envStaging,
    muted: s.muted,
    warn: s.tagWarn,
  };
  return <span className={cx(s.tag, variant ? map[variant] : undefined)}>{children}</span>;
}

export function CategoryChip({ category, fixable }: { category: string; fixable: boolean }) {
  return <span className={cx(s.cat, fixable ? s.catFixable : s.catInfra)}>{category}</span>;
}

/* ------------------------------------------------------------------ cards -- */

export function Meter({
  percent, color, small,
}: { percent: number; color: string; small?: boolean }) {
  const width = Math.max(0, Math.min(100, Number.isFinite(percent) ? percent : 0));
  return (
    <div className={cx(s.meter, small && s.meterSm)}>
      <span style={{ width: `${width}%`, background: color }} />
    </div>
  );
}

export function MeterCard({
  label, readout, percent, note, tone = 'ok',
}: {
  label: string;
  readout: string;
  percent: number;
  note: string;
  tone?: 'ok' | 'warn' | 'neutral';
}) {
  const color = tone === 'warn' ? 'var(--warn)' : tone === 'neutral' ? 'var(--neutral-bar)' : 'var(--ok)';
  return (
    <div className={cx(s.card, tone === 'warn' && s.cardWarn)}>
      <div className={s.cardHead}>
        <span>{label}</span>
        <b className={cx(tone === 'warn' && s.cardHeadHot)}>{readout}</b>
      </div>
      <Meter percent={percent} color={color} />
      <div className={s.cardNote}>{note}</div>
    </div>
  );
}

export function StatCard({
  label, value, note, tone,
}: {
  label: string;
  value: ReactNode;
  note?: string;
  tone?: 'hot' | 'cool' | 'plain';
}) {
  const map = { hot: s.toneHot, cool: s.toneCool, plain: s.tonePlain };
  return (
    <div className={cx(s.card, s.stat)}>
      <div className={s.statKey}>{label}</div>
      <div className={cx(s.statValue, tone && map[tone])}>{value}</div>
      {note ? <div className={s.statNote}>{note}</div> : null}
    </div>
  );
}

/* ---------------------------------------------------------------- banners -- */

export function Banner({
  tone = 'info', icon, title, detail,
}: {
  tone?: 'ok' | 'warn' | 'info';
  icon?: IconName;
  title: ReactNode;
  detail?: ReactNode;
}) {
  const map = { ok: s.bannerOk, warn: s.bannerWarn, info: s.bannerInfo };
  const strokes = { ok: 'var(--ok)', warn: 'var(--warn)', info: 'var(--accent)' };
  return (
    <div className={cx(s.banner, map[tone])}>
      {icon ? <Icon name={icon} stroke={strokes[tone]} /> : null}
      <div className={s.bannerTitle}>{title}</div>
      {detail ? <div className={s.bannerDetail}>{detail}</div> : null}
    </div>
  );
}

/* ----------------------------------------------------------- confirm bar -- */

/**
 * The inline confirmation every Run, Fix and Retry goes through. It sits above
 * the table, so a click on a row far down used to open it off-screen and look
 * like nothing happened: it scrolls itself into view and takes focus, and
 * Escape cancels.
 */
export function ConfirmBar({
  title, detail, note, confirmLabel, busyLabel, busy, onConfirm, onCancel,
}: {
  title: ReactNode;
  detail: ReactNode;
  /** An extra warning line, e.g. for a P0 crawler. */
  note?: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Instant, not smooth: a smooth scroll is driven by animation frames and
    // never moved in a backgrounded tab, leaving the bar off-screen.
    ref.current?.scrollIntoView({ block: 'nearest' });
    confirmRef.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div
      ref={ref}
      className={s.confirm}
      role="group"
      aria-label="Confirm action"
      onKeyDown={(e) => { if (e.key === 'Escape' && !busy) onCancel(); }}
    >
      <div className={s.confirmLeft}>
        <div className={s.confirmTitle}>{title}</div>
        <div className={s.confirmDetail}>{detail}</div>
        {note ? <div className={s.confirmP0}>{note}</div> : null}
      </div>
      <div className={s.confirmRight}>
        <button
          ref={confirmRef}
          type="button"
          className={cx(s.btn, s.primary, s.lg)}
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
        <Button tone="ghost" size="lg" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- sections -- */

export function Section({
  title, note, accent, children,
}: { title?: string; note?: ReactNode; accent?: boolean; children: ReactNode }) {
  return (
    <section className={cx(s.section, accent && s.sectionAccent)}>
      {title && note ? (
        <div className={s.sectionHead}>
          <h2>{title}</h2>
          <div className={s.sectionNote}>{note}</div>
        </div>
      ) : title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}

export function Check({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <div className={s.check}>
      <Icon name={ok ? 'check' : 'cross'} size={18} width={2.5} stroke={ok ? 'var(--ok)' : 'var(--warn)'} />
      <span>{children}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ misc -- */

export function EmptyState({
  title, detail, action,
}: { title: string; detail?: ReactNode; action?: ReactNode }) {
  return (
    <div className={s.empty}>
      <div className={s.emptyTitle}>{title}</div>
      {detail ? <div className={s.emptyDetail}>{detail}</div> : null}
      {action}
    </div>
  );
}

export function Skeleton({ height = 14, width }: { height?: number; width?: string }) {
  return <div className={s.skel} style={{ height, width }} />;
}

export { s as ui };
