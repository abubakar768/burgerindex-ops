'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { actionLabel, categoryLabel, streakLabel, utcDateLong } from '@/lib/format';
import type { TriageRow } from '@/lib/types';
import { useSession, useToast } from '@/components/Providers';
import { PageHeader } from '@/components/PageHeader';
import {
  Banner, Button, CategoryChip, EmptyState, FilterButton, NavButton, Pill, StatCard, ui,
} from '@/components/Primitives';
import { HeaderRow, Row, SkeletonRows, Table, TableFoot, cell } from '@/components/Table';
import s from './triage.module.css';

const COLS = '2.4fr 1.1fr 1.3fr 0.7fr 2.2fr 1.5fr';
const REFRESH_MS = 120_000;
const DAYS = 7;

type Filter = 'all' | 'p0' | 'fixable';

export default function TriagePage() {
  const { session } = useSession();
  const toast = useToast();
  const router = useRouter();

  const [filter, setFilter] = useState<Filter>('all');
  const [queueing, setQueueing] = useState<string | null>(null);

  const triage = usePoll((signal) => api.triage(DAYS, signal), REFRESH_MS);
  const spiders = usePoll((signal) => api.spiders(signal), 0);

  const rows = useMemo(() => triage.data ?? [], [triage.data]);

  const stats = useMemo(() => {
    const silent = rows.filter((r) => r.category === 'silent_drop');
    const lost = rows.filter((r) => r.category === 'lost');
    const failed = rows.filter((r) => r.category !== 'silent_drop' && r.category !== 'lost');
    const fixable = rows.filter((r) => r.fixable);
    return {
      failed,
      silent,
      lost,
      fixable,
      failedFixable: failed.filter((r) => r.fixable).length,
      p0: rows.filter((r) => r.p0),
    };
  }, [rows]);

  const p0Total = useMemo(
    () => (spiders.data ?? []).filter((sp) => sp.p0).length,
    [spiders.data],
  );

  const visible = useMemo(() => {
    if (filter === 'p0') return stats.p0;
    if (filter === 'fixable') return stats.fixable;
    return rows;
  }, [filter, rows, stats]);

  const startFix = useCallback(async (row: TriageRow) => {
    if (!row.jobId) {
      toast('This row has no job id, so auto-fix cannot be queued for it.');
      return;
    }
    setQueueing(row.jobId);
    try {
      const queued = await api.autofix(row.jobId, session.user);
      toast(`Auto-fix queued for ${queued.crawler}.`, 'ok');
      router.push(`/fix?task=${encodeURIComponent(queued.task_id)}`);
    } catch (cause) {
      const err = cause as { status?: number; detail?: string; message: string };
      toast(err.status === 404
        ? (err.detail ?? 'That job is no longer in the last 14 days.')
        : `Could not queue the fix: ${err.message}`);
      setQueueing(null);
    }
  }, [session.user, toast, router]);

  const p0Banner = spiders.loading
    ? null
    : stats.p0.length === 0
      ? (
        <Banner
          tone="ok"
          icon="shieldCheck"
          title={`P0 crawlers: ${p0Total} of ${p0Total} on time`}
          detail="No open P0 issues. A P0 failure alerts Slack through the worker's P0 watch."
        />
      )
      : (
        <Banner
          tone="warn"
          icon="warnTriangle"
          title={`P0 crawlers: ${Math.max(0, p0Total - stats.p0.length)} of ${p0Total} on time`}
          detail={`${stats.p0.length} P0 crawler${stats.p0.length === 1 ? '' : 's'} need attention: ${stats.p0.map((r) => r.crawler).join(', ')}`}
        />
      );

  return (
    <div className={ui.wrap}>
      <PageHeader
        eyebrow="MODULE / TRIAGE"
        title="Today's triage"
        subtitle={`${utcDateLong(new Date().toISOString())} · last ${DAYS} days of runs, worst first`}
        pills={triage.error
          ? <Pill tone="warn">{triage.error.isAuth ? 'Token rejected' : 'Disconnected'}</Pill>
          : null}
        actions={(
          <>
            <FilterButton
              label={`All · ${rows.length}`}
              active={filter === 'all'}
              onClick={() => setFilter('all')}
            />
            <FilterButton
              label={`P0 only · ${stats.p0.length}`}
              active={filter === 'p0'}
              onClick={() => setFilter('p0')}
            />
            <FilterButton
              label={`Code-fixable · ${stats.fixable.length}`}
              active={filter === 'fixable'}
              onClick={() => setFilter('fixable')}
            />
            <Button tone="solid" onClick={triage.refresh}>
              {triage.loading ? 'Syncing…' : 'Sync'}
            </Button>
            <NavButton href="/live">Live crawlers</NavButton>
          </>
        )}
      />

      {p0Banner}

      <div className={ui.gridStats}>
        <StatCard
          label="FAILED"
          value={triage.loading ? '—' : stats.failed.length}
          tone="hot"
          note={`${stats.failedFixable} need a code fix`}
        />
        <StatCard
          label="SILENT DROPS"
          value={triage.loading ? '—' : stats.silent.length}
          tone="hot"
          note="success, under 40% of baseline"
        />
        <StatCard
          label="LOST RUNS"
          value={triage.loading ? '—' : stats.lost.length}
          tone="plain"
          note="running far past their usual time"
        />
        <StatCard
          label="CODE-FIXABLE"
          value={triage.loading ? '—' : stats.fixable.length}
          tone="cool"
          note="Fix button available"
        />
      </div>

      <Table minWidth={1040}>
        <HeaderRow
          cols={COLS}
          labels={['CRAWLER', 'CLIENT', 'CATEGORY', 'STREAK', 'EVIDENCE', 'ACTION']}
        />

        {triage.error ? (
          <EmptyState
            title="Could not load triage"
            detail={triage.error.isOffline
              ? 'The API is unreachable. Triage also needs the dashboard API (DASHBOARD_API) to answer.'
              : triage.error.message}
            action={<Button tone="ghost" onClick={triage.refresh}>Try again</Button>}
          />
        ) : triage.loading ? (
          <SkeletonRows cols={COLS} count={8} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={rows.length ? 'Nothing matches this filter' : 'Nothing needs attention'}
            detail={rows.length
              ? 'Switch back to All to see every row.'
              : `No crawler failed, dropped silently or ran long in the last ${DAYS} days.`}
          />
        ) : (
          visible.map((row) => (
            <TriageTableRow
              key={`${row.crawler}-${row.jobId ?? row.category}`}
              row={row}
              busy={queueing === row.jobId}
              onFix={() => startFix(row)}
            />
          ))
        )}

        <TableFoot>
          Showing {visible.length} of {rows.length}. Fix runs a patched spider on 50 items first;
          nothing ships until someone approves it.
        </TableFoot>
      </Table>
    </div>
  );
}

function TriageTableRow({
  row, busy, onFix,
}: { row: TriageRow; busy: boolean; onFix: () => void }) {
  const hotStreak = row.streak >= 2;

  return (
    <Row cols={COLS}>
      <div className={cell.name}>{row.crawler}</div>

      <div className={cell.ink2}>{row.p0 ? 'P0' : '—'}</div>

      <div>
        <CategoryChip category={categoryLabel(row.category)} fixable={row.fixable} />
      </div>

      <div className={hotStreak ? s.streakHot : s.streakCalm}>{streakLabel(row.streak)}</div>

      <div className={s.evidence} title={row.evidence?.join(' · ')}>
        {row.evidence?.join(' · ') || '—'}
      </div>

      <div>
        {row.fixable ? (
          <Button tone="primary" size="sm" disabled={busy || !row.jobId} onClick={onFix}>
            {busy ? 'Queueing…' : 'Fix'}
          </Button>
        ) : (
          <span
            className={s.manualAction}
            title="The API has no endpoint for this yet — do it by hand, then re-run the crawler."
          >
            {actionLabel(row.action)}
            <span className={s.manualHint}>manual</span>
          </span>
        )}
      </div>
    </Row>
  );
}
