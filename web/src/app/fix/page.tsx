'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { parseDiff } from '@/lib/diff';
import { categoryLabel, utcStamp } from '@/lib/format';
import type { FixReport, TaskStatus } from '@/lib/types';
import { useSession, useToast } from '@/components/Providers';
import { PageHeader } from '@/components/PageHeader';
import {
  Button, CategoryChip, Check, EmptyState, Icon, NavButton, Pill, Section, cx, ui,
} from '@/components/Primitives';
import s from './fix.module.css';

/** autofix.pipeline.MAX_ATTEMPTS */
const MAX_ATTEMPTS = 3;
/** autofix.validate.validate(min_items=20) */
const MIN_ITEMS = 20;
const POLL_MS = 3_000;

export default function FixReviewPage() {
  return (
    <Suspense fallback={<div className={ui.wrap} />}>
      <FixReview />
    </Suspense>
  );
}

function FixReview() {
  const params = useSearchParams();
  const taskId = params.get('task');

  if (!taskId) {
    return (
      <div className={ui.wrap}>
        <PageHeader
          eyebrow="MODULE / FIX REVIEW"
          title="Fix review"
          back={<Link href="/triage" className={ui.backLink}>← Back to triage</Link>}
        />
        <EmptyState
          title="No fix selected"
          detail="Open this page from the Fix button on a code-fixable row in triage."
          action={<NavButton href="/triage">Go to triage</NavButton>}
        />
      </div>
    );
  }

  return <FixTask taskId={taskId} />;
}

function FixTask({ taskId }: { taskId: string }) {
  const { session } = useSession();
  const toast = useToast();
  const router = useRouter();

  const [approving, setApproving] = useState(false);
  const [mrUrl, setMrUrl] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const [settled, setSettled] = useState(false);

  // Poll while the Celery task is still running, then stop.
  const task = usePoll<TaskStatus>(
    (signal) => api.autofixStatus(taskId, signal),
    settled ? 0 : POLL_MS,
    [taskId],
  );

  useEffect(() => {
    const state = task.data?.state;
    if (state === 'SUCCESS' || state === 'FAILURE') setSettled(true);
  }, [task.data?.state]);

  const status = task.data;
  const report = status?.result ?? null;

  const approve = useCallback(async () => {
    if (!report) return;
    setApproving(true);
    try {
      const result = await api.approve(`${report.worktree}/report.json`, session.user);
      setMrUrl(result.mr_url);
      toast('Branch pushed and merge request opened.', 'ok');
    } catch (cause) {
      toast(`Approve failed: ${(cause as Error).message}`);
    } finally {
      setApproving(false);
    }
  }, [report, session.user, toast]);

  const retry = useCallback(async () => {
    if (!report?.jobId) return;
    setRetrying(true);
    try {
      const queued = await api.autofix(report.jobId, session.user);
      toast(`Another auto-fix queued for ${queued.crawler}.`, 'ok');
      router.push(`/fix?task=${encodeURIComponent(queued.task_id)}`);
    } catch (cause) {
      toast(`Retry failed: ${(cause as Error).message}`);
      setRetrying(false);
    }
  }, [report, session.user, toast, router]);

  const reject = useCallback(() => {
    toast('Rejected. The branch and report stay in the worktree for manual review.', 'ok');
    router.push('/triage');
  }, [toast, router]);

  const back = <Link href="/triage" className={ui.backLink}>← Back to triage</Link>;

  /* ----------------------------------------------------------- loading -- */

  if (!status) {
    return (
      <div className={ui.wrap}>
        <PageHeader eyebrow="MODULE / FIX REVIEW" title="Fix review" back={back} />
        {task.error ? (
          <EmptyState
            title="Could not read the fix task"
            detail={task.error.message}
            action={<Button tone="ghost" onClick={task.refresh}>Try again</Button>}
          />
        ) : (
          <EmptyState title="Loading the fix…" detail={`Task ${taskId}`} />
        )}
      </div>
    );
  }

  if (status.state === 'FAILURE') {
    return (
      <div className={ui.wrap}>
        <PageHeader
          eyebrow="MODULE / FIX REVIEW"
          title="Fix run failed"
          subtitle={`Task ${taskId}`}
          pills={<Pill tone="warn">Failed</Pill>}
          back={back}
        />
        <Section title="What the worker reported">
          <div className={s.actionNote}>{status.error || 'The worker gave no error message.'}</div>
          <div className={s.actionNote}>
            The worker needs git, scrapy, the crawlers clone at <code>AUTOFIX_REPO</code> and the
            Claude Code CLI on its machine. Check the Celery worker log for the traceback.
          </div>
        </Section>
      </div>
    );
  }

  if (!report) return <Working taskId={taskId} back={back} state={status.state} />;

  if (report.status === 'not_fixable') {
    return (
      <div className={ui.wrap}>
        <PageHeader
          eyebrow="MODULE / FIX REVIEW"
          title="Not a code fix"
          subtitle={`Task ${taskId}`}
          pills={<Pill tone="dashed">Not fixable</Pill>}
          back={back}
        />
        <EmptyState
          title={`${categoryLabel(report.category)} is not fixed by changing the spider`}
          detail={`The rules suggest: ${report.action}. Handle it by hand, then re-run the crawler.`}
          action={<NavButton href="/triage">Back to triage</NavButton>}
        />
      </div>
    );
  }

  return (
    <ReadyView
      report={report}
      back={back}
      approving={approving}
      retrying={retrying}
      mrUrl={mrUrl}
      onApprove={approve}
      onRetry={retry}
      onReject={reject}
    />
  );
}

/* ------------------------------------------------------------- working -- */

function Working({
  taskId, back, state,
}: { taskId: string; back: React.ReactNode; state: string }) {
  const steps = [
    'Checking out the crawlers repo on a fresh autofix branch',
    'Reading the saved evidence: log tail and bad responses',
    'Letting the agent diagnose and edit the spider',
    'Running a 50-item test crawl and validating the output',
    'Writing report.json with the diff and sample items',
  ];

  return (
    <div className={ui.wrap}>
      <PageHeader
        eyebrow="MODULE / FIX REVIEW"
        title="Fix in progress"
        subtitle={`Task ${taskId} · state ${state}`}
        pills={<Pill tone="accent">Running</Pill>}
        back={back}
      />
      <Section title="The worker is on it">
        <div className={s.working}>
          <span className={s.spin}><Icon name="spinner" size={22} stroke="var(--accent)" /></span>
          <div className={s.workingSteps}>
            {steps.map((step, i) => (
              <div key={step} className={s.workingStep}>
                <span className={s.stepNum}>{i + 1}</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
          <div className={s.actionNote}>
            Up to {MAX_ATTEMPTS} attempts, each with its own test crawl. Nothing is pushed:
            the branch stays local until someone approves it here. This page updates on its own.
          </div>
        </div>
      </Section>
    </div>
  );
}

/* --------------------------------------------------------------- ready -- */

function ReadyView({
  report, back, approving, retrying, mrUrl, onApprove, onRetry, onReject,
}: {
  report: FixReport;
  back: React.ReactNode;
  approving: boolean;
  retrying: boolean;
  mrUrl: string | null;
  onApprove: () => void;
  onRetry: () => void;
  onReject: () => void;
}) {
  const ready = report.status === 'ready_for_review';
  const last = report.attempts[report.attempts.length - 1];
  const diagnosis = last?.diagnosis;
  const diff = useMemo(() => parseDiff(report.diff), [report.diff]);

  const checks = useMemo(() => buildChecks(report), [report]);

  const sampleColumns = useMemo(() => {
    const first = report.sample_items?.[0];
    return first ? Object.keys(first).slice(0, 3) : [];
  }, [report.sample_items]);

  const sampleCols = sampleColumns.length === 3
    ? '2fr 1fr 1fr'
    : `repeat(${Math.max(1, sampleColumns.length)}, minmax(0, 1fr))`;

  return (
    <div className={ui.wrap}>
      <PageHeader
        eyebrow="MODULE / FIX REVIEW"
        title={`${report.crawler}: ${ready ? 'fix ready for review' : 'fix needs a human'}`}
        back={back}
        pills={ready
          ? <Pill tone="accent">Ready for review</Pill>
          : <Pill tone="warn">Needs a human</Pill>}
        subtitle={(
          <>
            Attempt {report.attempts.length} of {MAX_ATTEMPTS} · branch{' '}
            <span className={s.branch}>{report.branch}</span>
            {report.jobId ? ` · failed job ${report.jobId}` : ''}
            {report.created ? ` · started ${utcStamp(isoFromStamp(report.created))}` : ''}
          </>
        )}
      />

      <div className={ui.split}>
        <div className={cx(ui.splitMain, ui.splitCol)} style={{ display: 'flex' }}>
          <Section title="Why it failed">
            <div className={s.whyRow}>
              <CategoryChip
                category={categoryLabel(report.classification.category)}
                fixable={report.classification.fixable}
              />
              <span className={s.ruleNote}>
                Rule confidence {report.classification.confidence}
              </span>
            </div>
            <div className={ui.kv}>
              <div className={ui.kvKey}>Evidence</div>
              <div>{report.classification.evidence?.join(' · ') || '—'}</div>
              <div className={ui.kvKey}>Agent diagnosis</div>
              <div>{diagnosis?.root_cause || 'The agent returned no diagnosis.'}</div>
              {diagnosis?.change ? (
                <>
                  <div className={ui.kvKey}>Change made</div>
                  <div>{diagnosis.change}</div>
                </>
              ) : null}
              <div className={ui.kvKey}>Agent confidence</div>
              <div>{diagnosis?.confidence ?? '—'}</div>
            </div>
          </Section>

          <Section
            title="Code change"
            note={diff.files.length ? (
              <>
                <span className={ui.mono}>{diff.files.map((f) => f.path).join(', ')}</span>{' '}
                <span className={s.countAdd}>+{diff.added}</span>{' '}
                <span className={s.countDel}>−{diff.removed}</span>
              </>
            ) : 'no diff recorded'}
          >
            {diff.lines.length ? (
              <div className={s.diff}>
                <div className={s.diffInner}>
                  {diff.lines.map((line, i) => (
                    <div
                      key={i}
                      className={cx(
                        s.diffLine,
                        line.kind === 'hunk' && s.diffHunk,
                        line.kind === 'file' && s.diffFile,
                        line.kind === 'add' && s.diffAdd,
                        line.kind === 'del' && s.diffDel,
                        line.kind === 'ctx' && s.diffCtx,
                      )}
                    >
                      {line.text || ' '}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className={s.actionNote}>
                The agent made no file changes, so there is nothing to merge.
              </div>
            )}
          </Section>
        </div>

        <div className={cx(ui.splitSide, ui.splitCol)} style={{ display: 'flex' }}>
          <Section
            title="Test crawl"
            note={`${report.test.items} items`}
          >
            <div className={s.actionNote}>
              50-item limit, same settings as production
            </div>
            <div className={ui.checks}>
              {checks.map((c) => (
                <Check key={c.text} ok={c.ok}>{c.text}</Check>
              ))}
            </div>
          </Section>

          <Section
            title="Sample items"
            note={`${Math.min(5, report.sample_items?.length ?? 0)} of ${report.sample_items?.length ?? 0}`}
          >
            {sampleColumns.length ? (
              <div className={s.itemsScroll}>
                <div className={s.itemsTable}>
                  <div className={s.itemsHead} style={{ gridTemplateColumns: sampleCols }}>
                    {sampleColumns.map((key) => <div key={key}>{key.toUpperCase()}</div>)}
                  </div>
                  {report.sample_items.slice(0, 5).map((item, i) => (
                    <div key={i} className={s.itemsRow} style={{ gridTemplateColumns: sampleCols }}>
                      {sampleColumns.map((key, col) => (
                        <div
                          key={key}
                          className={cx(s.itemCell, col > 0 && s.itemMuted, col === 1 && ui.mono)}
                        >
                          {renderValue(item[key])}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className={s.actionNote}>The test crawl produced no items to sample.</div>
            )}
          </Section>

          <Section accent>
            {mrUrl ? (
              <>
                <div className={ui.bannerTitle}>Merge request opened</div>
                <a className={s.mrLink} href={mrUrl} target="_blank" rel="noreferrer noopener">
                  {mrUrl}
                </a>
                <div className={s.actionNote}>
                  Merging and deploying stay with your normal process.
                </div>
              </>
            ) : (
              <>
                <Button
                  tone="primary"
                  size="xl"
                  block
                  disabled={!ready || approving}
                  onClick={onApprove}
                >
                  {approving ? 'Pushing…' : 'Approve and open MR'}
                </Button>
                <div className={s.actionRow}>
                  <Button
                    tone="ghost"
                    size="lg"
                    flex1
                    disabled={retrying || !report.jobId}
                    onClick={onRetry}
                  >
                    {retrying ? 'Queueing…' : 'Retry fix'}
                  </Button>
                  <Button size="lg" flex1 onClick={onReject}>Reject</Button>
                </div>
                <div className={s.actionNote}>
                  {ready
                    ? 'Approve pushes the branch and opens a GitLab merge request. Retry queues a fresh attempt from the same failed job; the API takes no reviewer note yet. Reject leaves the branch in place and returns to triage.'
                    : 'This report is not ready for review, so Approve is closed: the test crawl did not pass validation. Read the problems above, then retry or fix it by hand.'}
                </div>
              </>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- helpers -- */

function buildChecks(report: FixReport): Array<{ ok: boolean; text: string }> {
  const problems = report.test.problems ?? [];
  const checks: Array<{ ok: boolean; text: string }> = [];

  const itemProblem = problems.find((p) => p.includes('items, need'));
  checks.push({
    ok: !itemProblem,
    text: `Items: ${report.test.items} (need ${MIN_ITEMS})`,
  });

  const schemaProblem = problems.find((p) => p.includes('fail schema'));
  if (schemaProblem) checks.push({ ok: false, text: schemaProblem });

  for (const [field, rate] of Object.entries(report.test.fill_rates ?? {})) {
    const problem = problems.find((p) => p.startsWith(`field '${field}'`));
    checks.push({
      ok: !problem,
      text: problem ?? `${field} filled ${Math.round(rate * 100)}%`,
    });
  }

  // Anything the loops above did not account for.
  for (const problem of problems) {
    const covered = checks.some((c) => c.text === problem);
    if (!covered && problem !== itemProblem) checks.push({ ok: false, text: problem });
  }

  return checks;
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** report.created is "20261009-041200" (UTC). */
function isoFromStamp(stamp: string): string | null {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/.exec(stamp);
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`;
}
