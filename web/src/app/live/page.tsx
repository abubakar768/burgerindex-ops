'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { ago, duration, gb, int, mb, sourceClass, sourceLabel } from '@/lib/format';
import type { Crawler, StopMode } from '@/lib/types';
import { useSession, useToast } from '@/components/Providers';
import { PageHeader } from '@/components/PageHeader';
import {
  Banner, Button, EmptyState, FilterButton, Meter, MeterCard, NavButton, Pill, Tag, cx, ui,
} from '@/components/Primitives';
import {
  CellStack, CellTags, HeaderRow, SelectableRow, SkeletonRows, Table, cell,
} from '@/components/Table';
import { LogPanel } from '@/components/live/LogPanel';
import { StopControls, type StopState, type StopStage } from '@/components/live/StopControls';
import s from '@/components/live/live.module.css';

const COLS = '2.4fr 0.8fr 1.6fr 0.9fr 0.9fr 0.9fr';
const REFRESH_MS = 30_000;

const HEARTBEAT_STALE_S = 120; // the designs turn the heartbeat column amber here
const RAM_HOT_PCT = 85;
const MEMORY_WARN_PCT = 75;

type SourceFilter = 'all' | 'scheduler' | 'dashboard' | 'manual';
const SOURCES: SourceFilter[] = ['all', 'scheduler', 'dashboard', 'manual'];

export default function LiveCrawlersPage() {
  const { session } = useSession();
  const toast = useToast();

  const [filter, setFilter] = useState<SourceFilter>('all');
  const [selectedPid, setSelectedPid] = useState<number | null>(null);
  const [stop, setStop] = useState<StopState | null>(null);
  const [stopping, setStopping] = useState(false);

  const server = usePoll((signal) => api.server(signal), REFRESH_MS);
  const crawlers = usePoll((signal) => api.crawlers(signal), REFRESH_MS);

  const rows = useMemo(() => crawlers.data ?? [], [crawlers.data]);

  // Keep a valid selection as crawls start and finish.
  useEffect(() => {
    if (!crawlers.data) return;
    const stillRunning = rows.some((c) => c.pid === selectedPid);
    if (!stillRunning) {
      setSelectedPid(rows.length > 0 ? rows[0].pid : null);
      setStop(null);
    }
  }, [crawlers.data, rows, selectedPid]);

  const selected = rows.find((c) => c.pid === selectedPid) ?? null;

  const counts = useMemo(() => {
    const by: Record<SourceFilter, number> = { all: rows.length, scheduler: 0, dashboard: 0, manual: 0 };
    for (const c of rows) {
      const key = String(c.source ?? '').toLowerCase() as SourceFilter;
      if (key in by && key !== 'all') by[key] += 1;
    }
    return by;
  }, [rows]);

  const visible = useMemo(
    () => (filter === 'all' ? rows : rows.filter((c) => String(c.source ?? '').toLowerCase() === filter)),
    [rows, filter],
  );

  const sendStop = useCallback(async (mode: StopMode) => {
    if (!selected) return;
    setStopping(true);
    try {
      await api.stop(selected.pid, { spider: selected.spider, mode, user: session.user });
      setStop({
        pid: selected.pid,
        stage: mode === 'kill' ? 'killed' : mode === 'force' ? 'forced' : 'stopping',
        at: Date.now(),
      });
      toast(
        `${mode === 'kill' ? 'SIGKILL' : 'SIGTERM'} sent to ${selected.spider} (PID ${selected.pid}).`,
        'ok',
      );
      crawlers.refresh();
    } catch (cause) {
      const err = cause as { status?: number; detail?: string; message: string };
      toast(err.status === 409 ? (err.detail ?? err.message) : `Stop failed: ${err.message}`);
      setStop(null);
    } finally {
      setStopping(false);
    }
  }, [selected, session.user, toast, crawlers]);

  const setStage = useCallback((stage: StopStage) => {
    if (!selected) return;
    setStop(stage === 'idle' ? null : { pid: selected.pid, stage, at: Date.now() });
  }, [selected]);

  /* ------------------------------------------------------------- header -- */

  const host = session.base
    ? (() => { try { return new URL(session.base).host; } catch { return session.base; } })()
    : (typeof window === 'undefined' ? '' : window.location.host);

  const subtitle = crawlers.data
    ? `${host} · ${rows.length} crawler${rows.length === 1 ? '' : 's'} running · updated every ${REFRESH_MS / 1000} s`
    : `${host} · loading…`;

  const statusPill = crawlers.error
    ? <Pill tone="warn">{crawlers.error.isAuth ? 'Token rejected' : 'Disconnected'}</Pill>
    : crawlers.loading
      ? <Pill tone="dashed">Loading…</Pill>
      : <Pill tone="ok">Live</Pill>;

  /* -------------------------------------------------------- server cards -- */

  const serverCards = (() => {
    if (!server.data) {
      return Array.from({ length: 4 }, (_, i) => (
        <div key={i} className={ui.card}><div className={ui.skel} style={{ height: 56 }} /></div>
      ));
    }

    const health = server.data;
    const memPct = health.memory.percent;
    const usedMb = health.memory.total_mb - health.memory.available_mb;
    const crawlerMb = rows.reduce((sum, c) => sum + (c.rss_mb || 0), 0);

    const swapPct = health.swap.percent;
    const swapUsed = health.swap.used_mb;
    const swapTotal = swapPct > 0 ? (swapUsed / swapPct) * 100 : null;

    const diskPath = Object.keys(health.disk)[0] ?? '/';
    const disk = health.disk[diskPath];

    const load1 = health.load_avg?.[0] ?? null;
    const cores = health.cpu_count || 1;

    return [
      <MeterCard
        key="mem"
        label="SERVER MEMORY"
        readout={`${Math.round(memPct)}%`}
        percent={memPct}
        tone={memPct >= MEMORY_WARN_PCT ? 'warn' : 'ok'}
        note={`${gb(usedMb)} of ${gb(health.memory.total_mb, 0)} GB · crawlers use ${gb(crawlerMb)} GB · alert at 85%`}
      />,
      <MeterCard
        key="swap"
        label="SWAP"
        readout={`${Math.round(swapPct)}%`}
        percent={swapPct}
        tone="neutral"
        note={swapTotal
          ? `${gb(swapUsed)} of ${gb(swapTotal, 0)} GB · any swap use slows crawlers`
          : `${gb(swapUsed)} GB used · any swap use slows crawlers`}
      />,
      <MeterCard
        key="disk"
        label={`DISK ${diskPath}`}
        readout={`${Math.round(disk?.percent ?? 0)}%`}
        percent={disk?.percent ?? 0}
        tone={(disk?.percent ?? 0) >= 90 ? 'warn' : 'ok'}
        note={disk ? `${disk.free_gb} GB free` : '—'}
      />,
      <MeterCard
        key="load"
        label="LOAD"
        readout={load1 === null ? '—' : load1.toFixed(1)}
        percent={load1 === null ? 0 : (load1 / cores) * 100}
        tone={load1 !== null && load1 > cores ? 'warn' : 'ok'}
        note={`1-min average · ${cores} core${cores === 1 ? '' : 's'}`}
      />,
    ];
  })();

  /* ------------------------------------------------------------- frozen -- */

  const frozen = rows.filter(
    (c) => c.heartbeat && c.heartbeat.age_seconds >= HEARTBEAT_STALE_S,
  );

  /* ------------------------------------------------------------- render -- */

  return (
    <div className={ui.wrap}>
      <PageHeader
        eyebrow="MODULE / LIVE_CRAWLERS"
        title="Live crawlers"
        subtitle={subtitle}
        pills={statusPill}
        actions={
          <>
            {SOURCES.map((src) => (
              <FilterButton
                key={src}
                label={src === 'all' ? `All · ${counts.all}` : `${sourceLabel(src)} · ${counts[src]}`}
                active={filter === src}
                onClick={() => setFilter(src)}
              />
            ))}
          </>
        }
      />

      <div className={ui.gridStats}>{serverCards}</div>

      {frozen.map((c) => {
        const mins = Math.round((c.heartbeat?.age_seconds ?? 0) / 60);
        const pct = c.limit_mb ? Math.round((c.rss_mb / c.limit_mb) * 100) : null;
        const ramClause = pct !== null && pct >= RAM_HOT_PCT ? ` and RAM at ${pct}% of its limit` : '';
        return (
          <Banner
            key={c.pid}
            tone="warn"
            icon="warnTriangle"
            title={`${c.spider} may be frozen`}
            detail={`No heartbeat for ${mins} min${ramClause}.`}
          />
        );
      })}

      <div className={ui.split}>
        <div className={ui.splitMain}>
          <Table minWidth={720}>
            <HeaderRow
              cols={COLS}
              labels={['SPIDER', 'RUNTIME', 'RAM / LIMIT', 'ITEMS', 'REQUESTS', 'HEARTBEAT']}
            />

            {crawlers.error ? (
              <EmptyState
                title="Could not load crawlers"
                detail={crawlers.error.message}
                action={<Button tone="ghost" onClick={crawlers.refresh}>Try again</Button>}
              />
            ) : crawlers.loading ? (
              <SkeletonRows cols={COLS} count={6} />
            ) : visible.length === 0 ? (
              <EmptyState
                title={rows.length ? 'No crawlers match this filter' : 'No crawlers running'}
                detail={rows.length
                  ? 'Switch the source filter to see the other running crawls.'
                  : 'Nothing is running on this machine right now.'}
                action={rows.length ? null : <NavButton href="/schedules">Go to schedules</NavButton>}
              />
            ) : (
              visible.map((c) => (
                <CrawlerRow
                  key={c.pid}
                  crawler={c}
                  selected={c.pid === selectedPid}
                  onSelect={() => {
                    setSelectedPid(c.pid);
                    if (stop && stop.pid !== c.pid) setStop(null);
                  }}
                />
              ))
            )}
          </Table>
        </div>

        <div className={ui.splitSide}>
          {selected ? (
            <div className={s.detail}>
              <div className={s.detailId}>
                <div className={s.detailName}>{selected.spider}</div>
                <div className={s.detailMeta}>
                  crawler PID {selected.pid} · sh wrapper PID {selected.wrapper_pid} · running{' '}
                  {duration(selected.runtime_seconds)}
                </div>
                <div className={s.detailBy}>
                  Started by <b>{sourceLabel(selected.source)}</b>
                  {selected.by ? ` · ${selected.by}` : ''}
                </div>
                {selected.cwd ? <div className={s.detailCwd}>{selected.cwd}</div> : null}
              </div>

              <div className={s.miniGrid}>
                <div className={s.mini}>
                  <div className={s.miniKey}>Items</div>
                  <div className={s.miniValue}>{selected.heartbeat ? int(selected.heartbeat.items) : '—'}</div>
                </div>
                <div className={s.mini}>
                  <div className={s.miniKey}>Requests</div>
                  <div className={s.miniValue}>{selected.heartbeat ? int(selected.heartbeat.requests) : '—'}</div>
                </div>
                <div className={s.mini}>
                  <div className={s.miniKey}>Errors</div>
                  <div className={s.miniValue}>{selected.heartbeat ? int(selected.heartbeat.errors) : '—'}</div>
                </div>
              </div>

              <LogPanel pid={selected.pid} logFile={selected.log_file} />

              <StopControls
                crawler={selected}
                state={stop}
                onStage={setStage}
                onSend={sendStop}
                busy={stopping}
              />
            </div>
          ) : (
            <div className={s.detail}>
              <EmptyState
                title="No crawler selected"
                detail="Pick a row to see its stats, log and stop controls."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CrawlerRow({
  crawler, selected, onSelect,
}: { crawler: Crawler; selected: boolean; onSelect: () => void }) {
  const hb = crawler.heartbeat;
  const limit = crawler.limit_mb ?? null;
  const ramPct = limit ? Math.min(100, Math.round((crawler.rss_mb / limit) * 100)) : null;
  const hot = ramPct !== null && ramPct >= RAM_HOT_PCT;
  const stale = Boolean(hb && hb.age_seconds >= HEARTBEAT_STALE_S);

  return (
    <SelectableRow
      cols={COLS}
      selected={selected}
      onSelect={onSelect}
      label={`${crawler.spider}, PID ${crawler.pid}`}
    >
      <CellStack>
        <span className={cell.name}>{crawler.spider}</span>
        <CellTags>
          <Tag variant={sourceClass(crawler.source)}>{sourceLabel(crawler.source)}</Tag>
          <Tag variant={crawler.env === 'prod' ? undefined : 'envStaging'}>{crawler.env || 'unknown'}</Tag>
          {crawler.p0 ? <Tag variant="srcManual">P0</Tag> : null}
          <span>PID {crawler.pid}{crawler.by ? ` · ${crawler.by}` : ''}</span>
        </CellTags>
      </CellStack>

      <span className={cell.ink2}>{duration(crawler.runtime_seconds)}</span>

      <CellStack>
        <span className={cx(s.ramLabel, hot ? s.ramHot : s.ramOk)}>
          {limit ? `${mb(crawler.rss_mb)} of ${mb(limit)} MB` : `${mb(crawler.rss_mb)} MB`}
        </span>
        {limit ? (
          <Meter percent={ramPct ?? 0} color={hot ? 'var(--warn)' : 'var(--ok)'} small />
        ) : (
          <span className={s.ramNone}>no limit configured</span>
        )}
      </CellStack>

      <span className={cell.mono}>{hb ? int(hb.items) : '—'}</span>
      <span className={cell.mono}>{hb ? int(hb.requests) : '—'}</span>
      <span className={stale ? s.hbStale : s.hbFresh}>
        {hb ? ago(hb.age_seconds) : 'no heartbeat'}
      </span>
    </SelectableRow>
  );
}
