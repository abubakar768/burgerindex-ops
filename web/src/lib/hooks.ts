'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from './api';

export interface PollState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  refresh: () => void;
}

/**
 * Fetch on mount, then on an interval. The fetcher receives an AbortSignal so a
 * refresh or unmount cancels the request in flight. `deps` restarts the poll.
 */
export function usePoll<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  deps: unknown[] = [],
): PollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | null = null;

    const run = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await fetcherRef.current(controller.signal);
        if (cancelled) return;
        setData(next);
        setError(null);
      } catch (cause) {
        if (cancelled || (cause as Error)?.name === 'AbortError') return;
        setError(cause instanceof ApiError ? cause : new ApiError(0, String(cause)));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    const timer = intervalMs > 0 ? setInterval(run, intervalMs) : null;

    return () => {
      cancelled = true;
      controller?.abort();
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, nonce, ...deps]);

  return { data, error, loading, refresh };
}

/** Re-renders every `ms` so countdown labels tick. Inactive when `active` is false. */
export function useTicker(active: boolean, ms = 1000): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setTick((t) => t + 1), ms);
    return () => clearInterval(timer);
  }, [active, ms]);

  return tick;
}

/** True once the component has mounted in the browser — guards localStorage reads. */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}
