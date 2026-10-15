import type { FailureCategory, RunSource } from './types';

export function int(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return '—';
  return Number(n).toLocaleString('en-US');
}

/** 9661 -> "2h 41m"; 362 -> "6m"; 42 -> "42s" */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.max(0, Math.round(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m`;
  return `${s}s`;
}

/** Heartbeat age in the designs' wording: "20 s ago" / "6 min ago". */
export function ago(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.max(0, Math.round(seconds));
  if (s >= 86400) return `${Math.round(s / 86400)} d ago`;
  if (s >= 3600) return `${Math.round(s / 3600)} h ago`;
  if (s >= 120) return `${Math.round(s / 60)} min ago`;
  return `${s} s ago`;
}

export function mb(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return int(Math.round(n));
}

export function gb(megabytes: number | null | undefined, digits = 1): string {
  if (megabytes === null || megabytes === undefined) return '—';
  return (megabytes / 1024).toFixed(digits);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function toDate(value: string | number | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null;
  // Process start times arrive as epoch seconds; job and schedule times as ISO.
  const d = typeof value === 'number'
    ? new Date(value * 1000)
    : new Date(String(value).replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "Oct 14, 00:00" — schedules and job times are UTC throughout. */
export function utcStamp(value: string | number | null | undefined): string {
  const d = toDate(value);
  if (!d) return '—';
  const date = `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
  const time = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
  return `${date}, ${time}`;
}

export function utcDate(value: string | number | null | undefined): string {
  const d = toDate(value);
  if (!d) return '—';
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

export function utcDateLong(value: string | number | null | undefined): string {
  const d = toDate(value);
  if (!d) return '—';
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** "3 hours ago" / "in 2 days" */
export function relative(value: string | number | null | undefined, now = Date.now()): string {
  const d = toDate(value);
  if (!d) return '—';
  const diff = Math.round((d.getTime() - now) / 1000);
  const abs = Math.abs(diff);
  const units: Array<[number, string]> = [[86400, 'day'], [3600, 'hour'], [60, 'minute']];
  for (const [secs, name] of units) {
    if (abs >= secs) {
      const n = Math.round(abs / secs);
      const label = `${n} ${name}${n === 1 ? '' : 's'}`;
      return diff < 0 ? `${label} ago` : `in ${label}`;
    }
  }
  return diff < 0 ? 'just now' : 'in a moment';
}

const CATEGORY_LABELS: Record<FailureCategory, string> = {
  endpoint_changed: 'Endpoint changed',
  blocked: 'Blocked',
  parse_broken: 'Parse broken',
  proxy_auth: 'Proxy auth',
  zyte_error: 'Zyte error',
  upstream_5xx: 'Upstream 5xx',
  network: 'Network',
  timeout: 'Timeout',
  shutdown: 'Shutdown',
  silent_drop: 'Silent drop',
  lost: 'Lost run',
  unknown: 'Unknown',
};

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return 'Unknown';
  return CATEGORY_LABELS[category as FailureCategory] ?? sentence(category);
}

const ACTION_LABELS: Record<string, string> = {
  fix: 'Fix',
  check_proxy_credentials: 'Check proxy',
  retry_zyte_alt: 'Retry with Zyte alt',
  retry: 'Retry',
  adjust_config: 'Adjust config',
  rerun: 'Rerun',
  investigate: 'Investigate',
  close_lost: 'Close run',
};

export function actionLabel(action: string | null | undefined): string {
  if (!action) return 'Investigate';
  return ACTION_LABELS[action] ?? sentence(action);
}

export function sentence(snake: string): string {
  const s = String(snake).replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function sourceLabel(source: RunSource | null | undefined): string {
  if (!source) return 'Unknown';
  return sentence(String(source));
}

/** Run source -> the chip modifier used in the designs. */
export function sourceClass(source: RunSource | null | undefined): string {
  const s = String(source ?? '').toLowerCase();
  if (s === 'scheduler') return 'srcScheduler';
  if (s === 'dashboard') return 'srcDashboard';
  if (s === 'manual') return 'srcManual';
  return 'muted';
}

export function streakLabel(streak: number): string {
  if (!streak) return '—';
  return `${streak} run${streak === 1 ? '' : 's'}`;
}
