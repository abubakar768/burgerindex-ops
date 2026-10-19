'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { frequency, nextRun, parseCron, timeLabel, type FrequencyGroup } from '@/lib/cron';
import { categoryLabel, relative, utcDate, utcStamp } from '@/lib/format';
import type { Schedule, TriageRow } from '@/lib/types';
import { useSession, useToast } from '@/components/Providers';
import { PageHeader } from '@/components/PageHeader';
import {
  Button, EmptyState, FilterButton, Pill, Tag, ui,
} from '@/components/Primitives';
import { HeaderRow, Row, SkeletonRows, Table, TableFoot, cell } from '@/components/Table';
import s from './schedules.module.css';

const COLS = '2.4fr 1.1fr 1.2fr 1.2fr 1.6fr 1.3fr';
const REFRESH_MS = 30_000;
const ISSUE_DAYS = 7;

type Group = 'all' | FrequencyGroup;
const GROUPS: Array<{ key: Group; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'daily', label: 'Daily' },
  { key: 'tri-weekly', label: 'Tri-weekly' },
  { key: 'weekly', label: 'Weekly' },
];

interface Decorated {
  schedule: Schedule;
  freqLabel: string;
  group: FrequencyGroup;
  times: string;
  next: Date | null;
  failure: TriageRow | null;
}

export default function SchedulesPage() {
  const { session } = useSession();
  const toast = useToast();

  const [search, setSearch] = useState('');
  const [group, setGroup] = useState<Group>('all');
  const [pending, setPending] = useState<Decorated | null>(null);
  const [queued, setQueued] = useState<string[]>([]);
  const [running, setRunning] = useState(false);

  const schedules = usePoll((signal) => api.schedules(signal), REFRESH_MS);
  // Used only to label the LAST RUN column: the scheduler DB stores a timestamp,
  // not an outcome, so a matching issue row is what makes a failure visible.
  const issues = usePoll((signal) => api.issues(ISSUE_DAYS, signal), 120_000);

  const failures = useMemo(() => {
    const byCrawler = new Map<string, TriageRow>();
    for (const row of issues.data ?? []) {
      if (!byCrawler.has(row.crawler)) byCrawler.set(row.crawler, row);
    }
    return byCrawler;
  }, [issues.data]);

  const decorated = useMemo<Decorated[]>(() => {
    const now = new Date();
    return (schedules.data ?? []).map((schedule) => {
      const cron = parseCron(schedule.schedule);
      const freq = frequency(cron);
      return {
        schedule,
        freqLabel: freq.label,
        group: freq.group,
        times: timeLabel(cron),
        next: schedule.enabled ? nextRun(cron, now) : null,
        failure: failures.get(schedule.spider) ?? null,
      };
    });
  }, [schedules.data, failures]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return decorated.filter((d) => {
      if (group !== 'all' && d.group !== group) return false;
      if (!needle) return true;
      return d.schedule.spider.toLowerCase().includes(needle)
        || String(d.schedule.client ?? '').toLowerCase().includes(needle);
    });
  }, [decorated, group, search]);

  const confirmRun = useCallback(async () => {
    if (!pending) return;
    const spider = pending.schedule.spider;
    setRunning(true);
    try {
      const result = await api.run(spider, session.user);
      setQueued((list) => [...list, spider]);
      setPending(null);
      toast(`${spider} started on prod as PID ${result.pid}.`, 'ok');
      schedules.refresh();
    } catch (cause) {
      const err = cause as { status?: number; detail?: string; message: string };
      toast(err.status === 409 || err.status === 404
        ? (err.detail ?? err.message)
        : `Run failed: ${err.message}`);
    } finally {
      setRunning(false);
    }
  }, [pending, session.user, toast, schedules]);

  /* --------------------------------------------------------- not set up -- */

  if (schedules.error?.isNotConfigured) {
    return (
      <div className={ui.wrap}>
        <Header count={null} actions={null} />
        <EmptyState
          title="Schedules are not configured"
          detail={(
            <>
              The API returned 501: <code>SCHEDULER_DB_URL</code> and <code>SCHEDULES_SQL</code> are
              not set in the ops <code>.env</code>. They point at a read-only user on the
              burgerindex-scheduler database. Verify the query with{' '}
              <code>python scripts/check_schedules.py</code>, then restart the API.
            </>
          )}
          action={<Button tone="ghost" onClick={schedules.refresh}>Try again</Button>}
        />
      </div>
    );
  }

  return (
    <div className={ui.wrap}>
      <Header
        count={schedules.data?.length ?? null}
        actions={(
          <>
            <label className="srOnly" htmlFor="sched-search">Search crawlers</label>
            <input
              id="sched-search"
              className={`${ui.input} ${ui.inputWide}`}
              type="search"
              placeholder="Search crawlers"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {GROUPS.map((g) => (
              <FilterButton
                key={g.key}
                label={g.key === 'all' ? `All · ${decorated.length}` : g.label}
                active={group === g.key}
                onClick={() => setGroup(g.key)}
              />
            ))}
          </>
        )}
      />

      {pending ? (
        <div className={ui.confirm}>
          <div className={ui.confirmLeft}>
            <div className={ui.confirmTitle}>
              Run <span className={ui.mono} style={{ fontWeight: 500 }}>
                {pending.schedule.spider}
              </span>{' '}now?
            </div>
            <div className={ui.confirmDetail}>
              Starts on prod as a dashboard run by {session.user}. Its next scheduled run
              ({pending.next ? utcStamp(pending.next.toISOString()) : 'unknown'}) stays as is.
            </div>
            {pending.schedule.p0 ? (
              <div className={ui.confirmP0}>
                P0 crawler: this adds a run on top of today&apos;s scheduled one.
              </div>
            ) : null}
          </div>
          <div className={ui.confirmRight}>
            <Button tone="primary" size="lg" disabled={running} onClick={confirmRun}>
              {running ? 'Starting…' : 'Run now'}
            </Button>
            <Button tone="ghost" size="lg" onClick={() => setPending(null)}>Cancel</Button>
          </div>
        </div>
      ) : null}

      <Table minWidth={1080}>
        <HeaderRow
          cols={COLS}
          labels={['CRAWLER', 'CLIENT', 'SCHEDULE', 'NEXT RUN', 'LAST RUN', 'ACTION']}
        />

        {schedules.error ? (
          <EmptyState
            title="Could not load schedules"
            detail={schedules.error.message}
            action={<Button tone="ghost" onClick={schedules.refresh}>Try again</Button>}
          />
        ) : schedules.loading ? (
          <SkeletonRows cols={COLS} count={8} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={decorated.length ? 'No crawlers match' : 'No schedules found'}
            detail={decorated.length
              ? 'Clear the search box or pick another frequency.'
              : 'SCHEDULES_SQL returned no rows. Check the query against the scheduler database.'}
          />
        ) : (
          visible.map((d) => (
            <ScheduleRow
              key={d.schedule.spider}
              row={d}
              queued={queued.includes(d.schedule.spider)}
              onAsk={() => setPending(d)}
            />
          ))
        )}

        <TableFoot>
          Run is disabled while a crawler is already running, so the same spider never runs
          twice at once.
        </TableFoot>
      </Table>
    </div>
  );
}

function Header({ count, actions }: { count: number | null; actions: React.ReactNode }) {
  return (
    <PageHeader
      eyebrow="MODULE / SCHEDULES"
      title="Scheduled crawlers"
      subtitle="From burgerindex-scheduler · times in UTC · Run starts a tagged prod run now and keeps the schedule as is"
      pills={count === null ? null : <Pill tone="ok">{count} scheduled</Pill>}
      actions={actions}
    />
  );
}

function ScheduleRow({
  row, queued, onAsk,
}: { row: Decorated; queued: boolean; onAsk: () => void }) {
  const { schedule, failure } = row;
  const isRunning = schedule.running_pid !== null && schedule.running_pid !== undefined;
  const isQueued = !isRunning && queued;

  const client = schedule.client || (schedule.p0 ? 'P0' : '—');

  return (
    <Row cols={COLS}>
      <div className={cell.name}>{schedule.spider}</div>

      <div className={cell.ink2}>{client}</div>

      <div className={s.stack}>
        <span>{row.freqLabel}</span>
        <span className={cell.sub}>{row.times}</span>
        {!schedule.enabled ? <Tag variant="muted">Paused</Tag> : null}
      </div>

      <div className={cell.ink2}>
        {!schedule.enabled
          ? '—'
          : row.next
            ? utcStamp(row.next.toISOString())
            : <span className={s.unknown} title={schedule.schedule}>unparsed cron</span>}
      </div>

      <div className={s.stack}>
        {failure ? (
          <>
            <span className={s.lastBad}>Failed · {categoryLabel(failure.category).toLowerCase()}</span>
            <span className={cell.sub}>
              {failure.started ? utcDate(failure.started) : '—'}
              {failure.evidence?.[0] ? ` · ${failure.evidence[0]}` : ''}
            </span>
          </>
        ) : schedule.last_run_at ? (
          <>
            <span className={s.lastOk}>Ran</span>
            <span className={cell.sub}>
              {utcDate(schedule.last_run_at)} · {relative(schedule.last_run_at)}
            </span>
          </>
        ) : (
          <>
            <span className={cell.sub}>No recorded run</span>
            <span className={cell.sub}>scheduler has no last_run_at</span>
          </>
        )}
      </div>

      <div>
        {isRunning ? (
          <Link href="/live" className={s.runningLink}>
            <span className={s.runningLabel}>Running</span>
            <span className={cell.sub}>PID {schedule.running_pid} · view live</span>
          </Link>
        ) : isQueued ? (
          <span className={s.queued}>
            <span className={s.queuedLabel}>Queued</span>
            <span className={cell.sub}>starting on prod</span>
          </span>
        ) : (
          <Button tone="primary" size="sm" onClick={onAsk}>Run</Button>
        )}
      </div>
    </Row>
  );
}
