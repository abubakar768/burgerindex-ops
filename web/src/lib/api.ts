'use client';

import { getActiveSession } from './session';
import type {
  ApproveResult, AutofixQueued, Crawler, LogTail, RunResult, Schedule,
  ServerHealth, Spider, StopMode, StopResult, TaskStatus, TriageRow,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly path: string;

  constructor(status: number, detail: string, path = '') {
    super(detail || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.path = path;
  }

  /** 501 from /schedules means SCHEDULER_DB_URL / SCHEDULES_SQL are unset. */
  get isNotConfigured(): boolean {
    return this.status === 501;
  }

  get isAuth(): boolean {
    return this.status === 401;
  }

  get isOffline(): boolean {
    return this.status === 0;
  }
}

export function apiUrl(path: string): string {
  return getActiveSession().base + path;
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal } = options;

  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method,
      signal,
      headers: {
        Authorization: `Bearer ${getActiveSession().token}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') throw cause;
    throw new ApiError(0, 'Cannot reach the API. Is uvicorn running?', path);
  }

  if (res.status === 204) return null as T;

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!res.ok) {
    const payload = data as { detail?: unknown; message?: unknown } | null;
    const raw = payload?.detail ?? payload?.message ?? text.slice(0, 300) ?? res.statusText;
    throw new ApiError(res.status, typeof raw === 'string' ? raw : JSON.stringify(raw), path);
  }

  return data as T;
}

export const api = {
  health: () => request<{ ok: boolean }>('/health'),

  server: (signal?: AbortSignal) => request<ServerHealth>('/server', { signal }),
  crawlers: (signal?: AbortSignal) => request<Crawler[]>('/crawlers', { signal }),
  logs: (pid: number, lines = 200, signal?: AbortSignal) =>
    request<LogTail>(`/crawlers/${pid}/logs?lines=${lines}`, { signal }),
  stop: (pid: number, body: { spider: string; mode: StopMode; user: string }) =>
    request<StopResult>(`/crawlers/${pid}/stop`, { method: 'POST', body }),

  spiders: (signal?: AbortSignal) => request<Spider[]>('/spiders', { signal }),
  schedules: (signal?: AbortSignal) => request<Schedule[]>('/schedules', { signal }),
  run: (spider: string, user: string) =>
    request<RunResult>(`/schedules/${encodeURIComponent(spider)}/run`, {
      method: 'POST',
      body: { user },
    }),

  // The endpoint was renamed from /triage; the backend still answers the old
  // path, but nothing here should call it.
  issues: (days = 7, signal?: AbortSignal) =>
    request<TriageRow[]>(`/issues?days=${days}`, { signal }),

  autofix: (jobId: string, user: string) =>
    request<AutofixQueued>('/autofix', { method: 'POST', body: { job_id: jobId, user } }),
  autofixStatus: (taskId: string, signal?: AbortSignal) =>
    request<TaskStatus>(`/autofix/${encodeURIComponent(taskId)}`, { signal }),
  approve: (reportPath: string, user: string) =>
    request<ApproveResult>('/autofix/approve', {
      method: 'POST',
      body: { report_path: reportPath, user },
    }),
};

/**
 * Live log lines from GET /crawlers/{pid}/logs/stream (server-sent events).
 *
 * EventSource cannot set an Authorization header and the endpoint takes no token
 * query parameter, so this reads the SSE body off fetch directly.
 * Returns an unsubscribe function.
 */
export function streamLogs(
  pid: number,
  handlers: { onLine: (line: string) => void; onError?: (error: ApiError) => void },
): () => void {
  const controller = new AbortController();

  void (async () => {
    let res: Response;
    try {
      res = await fetch(apiUrl(`/crawlers/${pid}/logs/stream`), {
        headers: {
          Authorization: `Bearer ${getActiveSession().token}`,
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
      });
    } catch (cause) {
      if ((cause as Error)?.name !== 'AbortError') {
        handlers.onError?.(new ApiError(0, 'Log stream could not start.'));
      }
      return;
    }

    if (!res.ok || !res.body) {
      const detail = await res.text().catch(() => '');
      handlers.onError?.(new ApiError(res.status, detail.slice(0, 200) || 'Log stream unavailable.'));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() ?? '';
        for (const chunk of chunks) {
          for (const line of chunk.split('\n')) {
            if (line.startsWith('data:')) handlers.onLine(line.slice(5).replace(/^ /, ''));
          }
        }
      }
    } catch (cause) {
      if ((cause as Error)?.name !== 'AbortError') {
        handlers.onError?.(new ApiError(0, 'Log stream dropped.'));
      }
    }
  })();

  return () => controller.abort();
}
