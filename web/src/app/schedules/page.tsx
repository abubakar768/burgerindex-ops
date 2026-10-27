'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { frequency, nextRun, parseCron, timeLabel, type FrequencyGroup } from '@/lib/cron';
import { categoryLabel, relative, utcDate, utcStamp } from '@/lib/format';
import type { Schedule, Spider, TriageRow } from '@/lib/types';
import { useSession, useToast } from '@/components/Providers';
import { PageHeader } from '@/components/PageHeader';
import {
  Button, ConfirmBar, EmptyState, FilterButton, Pill, Tag, ui,
} from '@/components/Primitives';
import { HeaderRow, Row, SkeletonRows, Table, TableFoot, cell } from '@/components/Table';
import s from './schedules.module.css';

const COLS = '2.4fr 1.1fr 1.2fr 1.2fr 1.6fr 1.3fr';
const SPIDER_COLS = '2.4fr 3.6fr 1.3fr';
const REFRESH_MS = 30_000;
// The API caches discovery; this only picks up a refresh done elsewhere.
const SPIDERS_MS = 300_000;
const ISSUE_DAYS = 7;

type View = 'scheduled' | 'unscheduled';

type Group = 'all' | FrequencyGroup;
const GROUPS: Array<{ key: Group; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'daily', label: 'Daily' },
  { key: 'every-few-days', label: 'Every few days' },
  { key: 'tri-weekly', label: 'Tri-weekly' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
];

interface Decorated {
  schedule: Schedule;
  freqLabel: string;
  group: FrequencyGroup;
  times: string;
  next: Date | null;
  failure: TriageRow | null;
}

/** What the confirm bar needs, from either view. */
interface Pending {
  spider: string;
  p0: boolean;
  /** The schedule's spider arguments, which Run does not pass. */
  args: string;
  /** null for a spider with no schedule */
  next: Date | null | undefined;
}

export default function SchedulesPage() {
  const { session } = useSession();
  const toast = useToast();

  const [view, setView] = useState<View>('scheduled');
  const [search, setSearch] = useState('');
  const [group, setGroup] = useState<Group>('all');
  const [pending, setPending] = useState<Pending | null>(null);
  const [queued, setQueued] = useState<string[]>([]);
  const [running, setRunning] = useState(false);

  const schedules = usePoll((signal) => api.schedules(signal), REFRESH_MS);
  const spiders = usePoll((signal) => api.spiders(signal), SPIDERS_MS);
  // Schedule rows carry running_pid; unscheduled spiders need the process list.
  const crawlers = usePoll((signal) => api.crawlers(signal), REFRESH_MS);
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

  const missing = useMemo(
    () => decorated.filter((d) => d.schedule.in_repo === false).length,
    [decorated],
  );

  const unscheduled = useMemo<Spider[]>(() => {
    if (!schedules.data || !spiders.data) return [];
    const scheduled = new Set(schedules.data.map((r) => r.spider));
    return spiders.data.filter((sp) => !scheduled.has(sp.spider));
  }, [schedules.data, spiders.data]);

  const runningPids = useMemo(() => {
    const byName = new Map<string, number>();
    for (const c of crawlers.data ?? []) byName.set(c.spider, c.pid);
    return byName;
  }, [crawlers.data]);

  const needle = search.trim().toLowerCase();

  const visible = useMemo(() => decorated.filter((d) => {
    if (group !== 'all' && d.group !== group) return false;
    if (!needle) return true;
    return d.schedule.spider.toLowerCase().includes(needle)
      || String(d.schedule.client ?? '').toLowerCase().includes(needle);
  }), [decorated, group, needle]);

  const visibleSpiders = useMemo(() => (needle
    ? unscheduled.filter((sp) => sp.spider.toLowerCase().includes(needle)
      || sp.file.toLowerCase().includes(needle))
    : unscheduled), [unscheduled, needle]);

  const confirmRun = useCallback(async () => {
    if (!pending) return;
    const { spider } = pending;
    setRunning(true);
    try {
      const result = await api.run(spider, session.user);
      setQueued((list) => [...list, spider]);
      setPending(null);
      toast(`${spider} started on prod as PID ${result.pid}.`, 'ok');
      schedules.refresh();
      crawlers.refresh();
    } catch (cause) {
      const err = cause as { status?: number; detail?: string; message: string };
      toast(err.status === 409 || err.status === 404
        ? (err.detail ?? err.message)
        : `Run failed: ${err.message}`);
    } finally {
      setRunning(false);
    }
  }, [pending, session.user, toast, schedules, crawlers]);

  const switchView = useCallback((next: View) => {
    setView(next);
    setPending(null);
  }, []);

  /* --------------------------------------------------------- not set up -- */

  if (schedules.error?.isNotConfigured) {
    return (
      <div className={ui.wrap}>
        <Header count={null} missing={0} actions={null} />
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

  const spidersReady = Boolean(schedules.data && spiders.data);

  return (
    <div className={ui.wrap}>
      <Header
        count={schedules.data?.length ?? null}
        missing={missing}
        actions={(
          <>
            <FilterButton
              label={`Scheduled${schedules.data ? ` · ${decorated.length}` : ''}`}
              active={view === 'scheduled'}
              onClick={() => switchView('scheduled')}
            />
            <FilterButton
              label={`Not scheduled${spidersReady ? ` · ${unscheduled.length}` : ''}`}
              active={view === 'unscheduled'}
              onClick={() => switchView('unscheduled')}
            />
            <span className={s.divider} aria-hidden />
            <label className="srOnly" htmlFor="sched-search">Search crawlers</label>
            <input
              id="sched-search"
              className={`${ui.input} ${ui.inputWide}`}
              type="search"
              placeholder="Search crawlers"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {view === 'scheduled' ? GROUPS.map((g) => (
              <FilterButton
                key={g.key}
                label={g.label}
                active={group === g.key}
                onClick={() => setGroup(g.key)}
              />
            )) : null}
          </>
        )}
      />

      {pending ? (
        <ConfirmBar
          key={pending.spider}
          title={(
            <>
              Run <span className={ui.mono} style={{ fontWeight: 500 }}>{pending.spider}</span> now?
            </>
          )}
          detail={(
            <>
              {pending.next === null
                ? `Starts on prod as a one-off dashboard run by ${session.user}. This spider has no schedule, so nothing runs it again afterwards.`
                : `Starts on prod as a dashboard run by ${session.user}. Its next scheduled run (${pending.next ? utcStamp(pending.next.toISOString()) : 'unknown'}) stays as is.`}
              {pending.args ? (
                <>
                  {' '}Runs without this schedule&apos;s arguments (
                  <span className={ui.mono}>{pending.args}</span>), so it does what the spider
                  does by default.
                </>
              ) : null}
            </>
          )}
          note={pending.p0 ? 'P0 crawler: this adds a run on top of today\'s scheduled one.' : undefined}
          confirmLabel="Run now"
          busyLabel="Starting…"
          busy={running}
          onConfirm={confirmRun}
          onCancel={() => setPending(null)}
        />
      ) : null}

      {view === 'scheduled' ? (
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
            // A spider can be scheduled twice under different task names, so
            // the spider alone is not a unique key.
            visible.map((d, i) => (
              <ScheduleRow
                key={`${d.schedule.spider}|${d.schedule.schedule}|${i}`}
                row={d}
                queued={queued.includes(d.schedule.spider)}
                onAsk={() => setPending({
                  spider: d.schedule.spider, p0: d.schedule.p0, args: d.schedule.args, next: d.next,
                })}
              />
            ))
          )}

          <TableFoot>
            Run is disabled while a crawler is already running, so the same spider never runs
            twice at once.
          </TableFoot>
        </Table>
      ) : (
        <Table minWidth={760}>
          <HeaderRow cols={SPIDER_COLS} labels={['CRAWLER', 'FILE', 'ACTION']} />

          {spiders.error ? (
            <EmptyState
              title="Could not load spiders"
              detail={spiders.error.message}
              action={<Button tone="ghost" onClick={spiders.refresh}>Try again</Button>}
            />
          ) : !spidersReady ? (
            <SkeletonRows cols={SPIDER_COLS} count={8} />
          ) : visibleSpiders.length === 0 ? (
            <EmptyState
              title={unscheduled.length ? 'No crawlers match' : 'Every spider is scheduled'}
              detail={unscheduled.length
                ? 'Clear the search box.'
                : 'Each spider in the crawlers repo has at least one schedule.'}
            />
          ) : (
            visibleSpiders.map((sp) => (
              <SpiderRow
                key={sp.spider}
                spider={sp}
                runningPid={runningPids.get(sp.spider) ?? null}
                queued={queued.includes(sp.spider)}
                onAsk={() => setPending({ spider: sp.spider, p0: sp.p0, args: '', next: null })}
              />
            ))
          )}

          <TableFoot>
            Spiders in the crawlers repo with no schedule in burgerindex-scheduler. Run starts a
            one-off; to run one regularly, add it to the scheduler.
          </TableFoot>
        </Table>
      )}
    </div>
  );
}

function Header({
  count, missing, actions,
}: { count: number | null; missing: number; actions: React.ReactNode }) {
  return (
    <PageHeader
      eyebrow="MODULE / SCHEDULES"
      title="Scheduled crawlers"
      subtitle="From burgerindex-scheduler · times in UTC · Run starts a tagged prod run now and keeps the schedule as is"
      pills={count === null ? null : (
        <>
          <Pill tone="ok">{count} scheduled</Pill>
          {missing ? <Pill tone="warn">{missing} not in crawlers repo</Pill> : null}
        </>
      )}
      actions={actions}
    />
  );
}

function RunAction({
  runningPid, queued, disabledReason, onAsk,
}: {
  runningPid: number | null | undefined;
  queued: boolean;
  disabledReason?: string;
  onAsk: () => void;
}) {
  if (runningPid !== null && runningPid !== undefined) {
    return (
      <Link href="/live" className={s.runningLink}>
        <span className={s.runningLabel}>Running</span>
        <span className={cell.sub}>PID {runningPid} · view live</span>
      </Link>
    );
  }
  if (queued) {
    return (
      <span className={s.queued}>
        <span className={s.queuedLabel}>Queued</span>
        <span className={cell.sub}>starting on prod</span>
      </span>
    );
  }
  return (
    <Button
      tone="primary"
      size="sm"
      onClick={onAsk}
      disabled={Boolean(disabledReason)}
      title={disabledReason}
    >
      Run
    </Button>
  );
}

function ScheduleRow({
  row, queued, onAsk,
}: { row: Decorated; queued: boolean; onAsk: () => void }) {
  const { schedule, failure } = row;
  const client = schedule.client || (schedule.p0 ? 'P0' : '—');

  return (
    <Row cols={COLS}>
      <div className={s.stack}>
        <span className={cell.name}>{schedule.spider}</span>
        {schedule.args ? <span className={`${cell.sub} ${ui.mono}`}>{schedule.args}</span> : null}
        {schedule.in_repo === false ? <Tag variant="warn">Not in crawlers repo</Tag> : null}
      </div>

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
        <RunAction
          runningPid={schedule.running_pid}
          queued={queued}
          disabledReason={schedule.in_repo !== false
            ? undefined
            : 'No spider with this name in the crawlers repo, so the scheduler\'s runs of it fail too. Rename or remove the schedule.'}
          onAsk={onAsk}
        />
      </div>
    </Row>
  );
}

function SpiderRow({
  spider, runningPid, queued, onAsk,
}: { spider: Spider; runningPid: number | null; queued: boolean; onAsk: () => void }) {
  return (
    <Row cols={SPIDER_COLS}>
      <div className={s.stack}>
        <span className={cell.name}>{spider.spider}</span>
        {spider.p0 ? <Tag variant="warn">P0</Tag> : null}
      </div>
      <div className={cell.mono}>{spider.file}</div>
      <div>
        <RunAction runningPid={runningPid} queued={queued} onAsk={onAsk} />
      </div>
    </Row>
  );
}
