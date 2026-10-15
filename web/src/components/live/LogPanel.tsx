'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiError, api, streamLogs } from '@/lib/api';
import s from './live.module.css';

const TAIL_LINES = 200;
const MAX_KEPT = 500;
const HOT = /\b(ERROR|WARNING|CRITICAL|Traceback)\b/;

/**
 * The last lines of a crawler's log, then live ones over server-sent events.
 * The tail is fetched first so the panel is never empty while waiting for the
 * next write.
 */
export function LogPanel({ pid, logFile }: { pid: number; logFile: string | null }) {
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [streaming, setStreaming] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  useEffect(() => {
    setLines([]);
    setError(null);
    setStreaming(false);

    if (!logFile) {
      setError(new ApiError(404, 'This crawler does not write to a log file.'));
      return undefined;
    }

    let cancelled = false;
    const controller = new AbortController();

    api.logs(pid, TAIL_LINES, controller.signal)
      .then((tail) => {
        if (cancelled) return;
        setLines(tail.lines.map((line) => line.replace(/\n$/, '')));
      })
      .catch((cause) => {
        if (cancelled || (cause as Error)?.name === 'AbortError') return;
        setError(cause instanceof ApiError ? cause : new ApiError(0, String(cause)));
      });

    const unsubscribe = streamLogs(pid, {
      onLine: (line) => {
        if (cancelled) return;
        setStreaming(true);
        setLines((prev) => {
          const next = [...prev, line];
          return next.length > MAX_KEPT ? next.slice(-MAX_KEPT) : next;
        });
      },
      // The tail above still stands if the stream cannot start; no need to shout.
      onError: () => setStreaming(false),
    });

    return () => {
      cancelled = true;
      controller.abort();
      unsubscribe();
    };
  }, [pid, logFile]);

  // Follow the tail only while the reader is already at the bottom.
  useEffect(() => {
    const box = boxRef.current;
    if (box && pinnedRef.current) box.scrollTop = box.scrollHeight;
  }, [lines]);

  function onScroll() {
    const box = boxRef.current;
    if (!box) return;
    pinnedRef.current = box.scrollTop + box.clientHeight >= box.scrollHeight - 24;
  }

  return (
    <div className={s.logWrap}>
      <div className={s.logHead}>
        <span>LOG</span>
        <span>
          {error ? 'unavailable' : streaming ? 'live · server-sent events' : 'last lines'}
        </span>
      </div>
      <div className={s.log} ref={boxRef} onScroll={onScroll}>
        {error ? (
          <div className={`${s.logLine} ${s.logDim}`}>{error.detail || error.message}</div>
        ) : lines.length === 0 ? (
          <div className={`${s.logLine} ${s.logDim}`}>Waiting for log lines…</div>
        ) : (
          lines.map((line, i) => (
            <div key={`${i}-${line.slice(0, 24)}`} className={`${s.logLine} ${HOT.test(line) ? s.logHot : ''}`}>
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
