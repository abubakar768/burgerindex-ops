// Shapes returned by the burgerindex-ops API (app/routers/*.py).

export interface Heartbeat {
  spider: string;
  pid: number;
  state: 'running' | 'finished';
  ts: number;
  age_seconds: number;
  rss_mb: number;
  items: number;
  requests: number;
  responses: number;
  errors: number;
  retries: number;
  dropped: number;
  finish_reason: string | null;
}

export type RunSource = 'scheduler' | 'dashboard' | 'manual' | string;

/** GET /crawlers */
export interface Crawler {
  pid: number;
  wrapper_pid: number;
  spider: string;
  user: string;
  status: string;
  started: number;
  runtime_seconds: number;
  rss_mb: number;
  cpu_percent: number;
  log_file: string | null;
  source: RunSource;
  by: string | null;
  env: string;
  cwd: string | null;
  heartbeat: Heartbeat | null;
  p0: boolean;
  /** Present when MEMUSAGE_LIMIT_MB is set in the ops .env. */
  limit_mb?: number | null;
}

/** GET /server */
export interface ServerHealth {
  memory: { total_mb: number; available_mb: number; percent: number };
  swap: { used_mb: number; percent: number };
  load_avg: [number, number, number];
  cpu_count: number;
  disk: Record<string, { percent: number; free_gb: number }>;
}

/** GET /crawlers/{pid}/logs */
export interface LogTail {
  pid: number;
  log_file: string;
  lines: string[];
}

export type StopMode = 'graceful' | 'force' | 'kill';

export interface StopResult {
  ok: boolean;
  pid: number;
  spider: string;
  signal: string;
  mode: StopMode;
}

/** GET /spiders */
export interface Spider {
  spider: string;
  file: string;
  p0: boolean;
}

/** GET /schedules */
export interface Schedule {
  spider: string;
  /** Spider arguments the scheduler passes after the name, e.g. "-a hour=8:00"; "" if none. */
  args: string;
  /** django_celery_beat crontab: "minute hour day_of_month month_of_year day_of_week" */
  schedule: string;
  enabled: boolean;
  last_run_at?: string | null;
  client?: string | null;
  running_pid: number | null;
  p0: boolean;
  /**
   * False when no spider of this name is in CRAWLERS_DIR: every scheduled run of
   * it fails. Null when the API only has the source scan (`scrapy list` failed),
   * which misses composed names, so "missing" cannot be told apart from "unseen".
   */
  in_repo: boolean | null;
}

/** POST /schedules/{spider}/run */
export interface RunResult {
  pid: number;
  spider: string;
  source: string;
  by: string;
  log_file: string;
  started: string;
  cwd: string;
}

export type FailureCategory =
  | 'endpoint_changed' | 'blocked' | 'parse_broken' | 'proxy_auth' | 'zyte_error'
  | 'upstream_5xx' | 'network' | 'timeout' | 'shutdown' | 'silent_drop' | 'lost' | 'unknown';

/** GET /issues (formerly /triage) */
export interface TriageRow {
  crawler: string;
  jobId: string | null;
  status: string | null;
  started: string | null;
  p0: boolean;
  streak: number;
  category: FailureCategory;
  action: string;
  fixable: boolean;
  confidence: number;
  evidence: string[];
}

export interface Classification {
  category: FailureCategory;
  action: string;
  fixable: boolean;
  confidence: number;
  evidence: string[];
}

export interface FixDiagnosis {
  session_id?: string | null;
  root_cause?: string | null;
  change?: string | null;
  confidence?: number | null;
}

export interface FixValidation {
  ok: boolean;
  items: number;
  problems: string[];
  fill_rates: Record<string, number>;
  sample: unknown[];
}

export interface FixAttempt {
  attempt: number;
  diagnosis: FixDiagnosis;
  validation: FixValidation;
}

/** autofix/pipeline.py `run()` -> report.json */
export interface FixReport {
  status: 'ready_for_review' | 'needs_human' | 'not_fixable';
  crawler: string;
  jobId: string | null;
  branch: string;
  worktree: string;
  classification: Classification;
  attempts: FixAttempt[];
  diff: string;
  test: { items: number; fill_rates: Record<string, number>; problems: string[] };
  sample_items: Record<string, unknown>[];
  created: string;
  /** Only on the not_fixable short-circuit. */
  category?: string;
  action?: string;
}

export type TaskState = 'PENDING' | 'STARTED' | 'RETRY' | 'SUCCESS' | 'FAILURE';

/** GET /autofix/{task_id} */
export interface TaskStatus {
  task_id: string;
  state: TaskState;
  result: FixReport | null;
  error: string | null;
}

/** POST /autofix */
export interface AutofixQueued {
  task_id: string;
  crawler: string;
}

/** POST /autofix/approve */
export interface ApproveResult {
  mr_url: string;
}
