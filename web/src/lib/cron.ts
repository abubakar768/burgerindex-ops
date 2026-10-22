// Cron handling for the Schedules page.
//
// SCHEDULES_SQL returns django_celery_beat's crontab fields joined in order:
//   minute hour day_of_month month_of_year day_of_week
// Celery matches day_of_month AND day_of_week (unlike Vixie cron, which ORs them
// when both are restricted), so that is what nextRun does. All times are UTC.

export interface CronField {
  any: boolean;
  values: number[];
}

export interface Cron {
  minute: CronField;
  hour: CronField;
  dom: CronField;
  month: CronField;
  dow: CronField;
  raw: string;
}

export type FrequencyGroup = 'daily' | 'every-few-days' | 'weekly' | 'tri-weekly' | 'monthly' | 'other';

export interface Frequency {
  label: string;
  group: FrequencyGroup;
}

const DOW_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DOW_WORDS: Record<string, number> = {
  sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
};
const MONTH_WORDS: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

function range(min: number, max: number): number[] {
  return Array.from({ length: max - min + 1 }, (_, i) => min + i);
}

function token(raw: string, words?: Record<string, number>): number | null {
  const text = raw.trim();
  if (words && text in words) return words[text];
  const n = Number(text);
  return Number.isInteger(n) ? n : null;
}

function parseField(
  raw: string | undefined,
  min: number,
  max: number,
  words?: Record<string, number>,
): CronField | null {
  const text = String(raw ?? '*').trim().toLowerCase();
  if (text === '' || text === '*') return { any: true, values: range(min, max) };

  const out = new Set<number>();
  for (const part of text.split(',')) {
    const [spec, stepRaw] = part.split('/');
    const step = stepRaw ? Number(stepRaw) : 1;
    if (!Number.isFinite(step) || step < 1) return null;

    let lo: number | null;
    let hi: number | null;
    if (spec === '*' || spec === '') {
      lo = min;
      hi = max;
    } else if (spec.includes('-')) {
      const [a, b] = spec.split('-');
      lo = token(a, words);
      hi = token(b, words);
    } else {
      lo = token(spec, words);
      hi = lo;
    }

    if (lo === null || hi === null || hi < lo) return null;
    for (let v = lo; v <= hi; v += step) {
      if (v >= min && v <= max) out.add(v);
    }
  }

  if (out.size === 0) return null;
  return { any: false, values: [...out].sort((a, b) => a - b) };
}

/** Parse "5 2,11 * * *" into fields, or null when the string is not a cron. */
export function parseCron(expression: string | null | undefined): Cron | null {
  if (!expression) return null;
  const parts = String(expression).trim().split(/\s+/);
  if (parts.length < 5) return null;

  const minute = parseField(parts[0], 0, 59);
  const hour = parseField(parts[1], 0, 23);
  const dom = parseField(parts[2], 1, 31);
  const month = parseField(parts[3], 1, 12, MONTH_WORDS);
  let dow = parseField(parts[4], 0, 7, DOW_WORDS);
  if (!minute || !hour || !dom || !month || !dow) return null;

  // Cron allows 7 for Sunday; fold it onto 0.
  dow = dow.any
    ? { any: true, values: range(0, 6) }
    : { any: false, values: [...new Set(dow.values.map((d) => (d === 7 ? 0 : d)))].sort((a, b) => a - b) };

  return { minute, hour, dom, month, dow, raw: String(expression).trim() };
}

/** Next firing strictly after `from`, in UTC. Null if none within a year. */
export function nextRun(cron: Cron | null, from: Date = new Date()): Date | null {
  if (!cron) return null;

  for (let offset = 0; offset <= 400; offset += 1) {
    const day = new Date(Date.UTC(
      from.getUTCFullYear(), from.getUTCMonth(), from.getUTCDate() + offset,
    ));
    if (!cron.month.values.includes(day.getUTCMonth() + 1)) continue;
    if (!cron.dom.values.includes(day.getUTCDate())) continue;
    if (!cron.dow.values.includes(day.getUTCDay())) continue;

    for (const h of cron.hour.values) {
      for (const m of cron.minute.values) {
        const at = new Date(Date.UTC(
          day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), h, m,
        ));
        if (at.getTime() > from.getTime()) return at;
      }
    }
  }
  return null;
}

/** "Daily" / "4x daily" / "Tri-weekly" / "Weekly" / "Hourly" / "Monthly". */
export function frequency(cron: Cron | null): Frequency {
  if (!cron) return { label: 'Custom', group: 'other' };

  const perDay = cron.hour.values.length * cron.minute.values.length;

  if (cron.minute.any) return { label: 'Every minute', group: 'other' };
  if (cron.hour.any && cron.dow.any && cron.dom.any) return { label: 'Hourly', group: 'other' };
  if (!cron.dom.any) {
    // The scheduler fakes "every N days" and some weeklies with day-of-month
    // lists (every_3_days = 1,4,7,...,28; weekly_3am = 1,7,14,21,28), so the
    // count of days is what says how often it runs, not the field it is in.
    const n = cron.dom.values.length;
    if (n === 1) return { label: 'Monthly', group: 'monthly' };
    if (n === 2) return { label: 'Twice monthly', group: 'monthly' };
    if (n <= 6) return { label: 'Weekly', group: 'weekly' };
    return { label: `Every ${Math.round(30 / n)} days`, group: 'every-few-days' };
  }

  if (!cron.dow.any && cron.dow.values.length < 7) {
    const days = cron.dow.values.length;
    if (days === 1) return { label: 'Weekly', group: 'weekly' };
    if (days === 2) return { label: 'Twice weekly', group: 'weekly' };
    if (days === 3) return { label: 'Tri-weekly', group: 'tri-weekly' };
    return { label: `${days}× weekly`, group: 'weekly' };
  }

  if (perDay === 1) return { label: 'Daily', group: 'daily' };
  return { label: `${perDay}× daily`, group: 'daily' };
}

/** "02:05, 11:05, 15:05, 22:05" or "Mon, Wed, Fri 04:00". */
export function timeLabel(cron: Cron | null): string {
  if (!cron) return '';
  if (cron.minute.any || cron.hour.any) return cron.raw;

  const times: string[] = [];
  for (const h of cron.hour.values) {
    for (const m of cron.minute.values) {
      times.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
      if (times.length > 8) return `${times.length}+ times a day`;
    }
  }

  const dayPart = cron.dow.any || cron.dow.values.length === 7
    ? ''
    : `${cron.dow.values.map((d) => DOW_NAMES[d]).join(', ')} `;
  const dom = cron.dom.values;
  const domPart = cron.dom.any
    ? ''
    : dom.length > 4
      ? `days ${dom[0]}, ${dom[1]} … ${dom[dom.length - 1]} · `
      : `day ${dom.join(', ')} · `;

  return `${domPart}${dayPart}${times.join(', ')}`.trim();
}
