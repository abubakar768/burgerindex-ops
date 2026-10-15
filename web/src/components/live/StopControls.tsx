'use client';

import { Button } from '@/components/Primitives';
import { duration } from '@/lib/format';
import { useTicker } from '@/lib/hooks';
import type { Crawler, StopMode } from '@/lib/types';
import s from './live.module.css';

/** The designs unlock Force stop 2 min after SIGTERM, and Kill 30 s after Force. */
export const FORCE_UNLOCK_MS = 120_000;
export const KILL_UNLOCK_MS = 30_000;

export type StopStage = 'idle' | 'confirm' | 'stopping' | 'forced' | 'killed';

export interface StopState {
  pid: number;
  stage: StopStage;
  at: number;
}

export function StopControls({
  crawler, state, onStage, onSend, busy,
}: {
  crawler: Crawler;
  state: StopState | null;
  onStage: (stage: StopStage) => void;
  onSend: (mode: StopMode) => void;
  busy: boolean;
}) {
  const stage: StopStage = state && state.pid === crawler.pid ? state.stage : 'idle';
  const live = stage === 'stopping' || stage === 'forced';

  // Re-render each second so the unlock countdowns tick.
  useTicker(live);
  const since = state && live ? Date.now() - state.at : 0;

  if (stage === 'idle') {
    return (
      <div className={s.stopBox}>
        <div className={s.stopRow}>
          <Button tone="warn" size="lg" grow onClick={() => onStage('confirm')}>Stop</Button>
          <Button size="lg" grow disabled>Force stop</Button>
          <Button size="lg" grow disabled>Kill</Button>
        </div>
        <div className={s.stopNote}>
          Stop sends SIGTERM to the crawler PID: it finishes in-flight requests and saves its
          stats. Force stop unlocks 2 min later, Kill 30 s after that.
        </div>
      </div>
    );
  }

  if (stage === 'confirm') {
    return (
      <div className={s.stopBox}>
        <div className={s.stopConfirm}>
          <div className={s.stopConfirmTitle}>Stop {crawler.spider}?</div>
          <div className={s.stopConfirmDetail}>
            Sends SIGTERM to PID {crawler.pid}. The run ends as &quot;shutdown&quot; and today&apos;s
            data stops here.
          </div>
          <div className={s.stopConfirmRow}>
            <Button tone="warnSolid" size="lg" flex1 disabled={busy} onClick={() => onSend('graceful')}>
              {busy ? 'Sending…' : 'Confirm stop'}
            </Button>
            <Button tone="ghost" size="lg" flex1 onClick={() => onStage('idle')}>Cancel</Button>
          </div>
        </div>
      </div>
    );
  }

  if (stage === 'stopping') {
    const unlocked = since >= FORCE_UNLOCK_MS;
    const left = Math.max(0, Math.ceil((FORCE_UNLOCK_MS - since) / 1000));
    return (
      <div className={s.stopBox}>
        <div className={s.stopStack}>
          <div className={s.stopState}>
            <span className={s.dot} />
            Stopping gracefully · SIGTERM sent {duration(since / 1000)} ago
          </div>
          <div className={s.stopRowTight}>
            <Button size="lg" grow disabled>Stop</Button>
            <Button
              tone={unlocked ? 'warn' : 'default'}
              size="lg"
              grow
              disabled={!unlocked || busy}
              onClick={() => onSend('force')}
            >
              {unlocked ? 'Force stop' : `Force stop · ${left}s`}
            </Button>
            <Button size="lg" grow disabled>Kill</Button>
          </div>
          <div className={s.stopNote}>
            {unlocked
              ? 'Still running after 2 min, so Force stop is open (a second SIGTERM). Kill (SIGKILL) unlocks 30 s later; after a Kill the job is marked "killed" because no stats are saved.'
              : 'Scrapy is closing in-flight requests and writing its stats. Force stop unlocks after 2 min.'}
          </div>
        </div>
      </div>
    );
  }

  if (stage === 'forced') {
    const unlocked = since >= KILL_UNLOCK_MS;
    const left = Math.max(0, Math.ceil((KILL_UNLOCK_MS - since) / 1000));
    return (
      <div className={s.stopBox}>
        <div className={s.stopStack}>
          <div className={s.stopState}>
            <span className={s.dot} />
            Force stop sent · {unlocked ? 'process still alive after 30 s' : 'waiting 30 s'}
          </div>
          <div className={s.stopRowTight}>
            <Button size="lg" grow disabled>Stop</Button>
            <Button size="lg" grow disabled>Force stop</Button>
            <Button
              tone={unlocked ? 'danger' : 'default'}
              size="lg"
              grow
              disabled={!unlocked || busy}
              onClick={() => onSend('kill')}
            >
              {unlocked ? 'Kill' : `Kill · ${left}s`}
            </Button>
          </div>
          <div className={s.stopNote}>
            Kill sends SIGKILL to PID {crawler.pid} and any child browsers. Nothing is saved.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={s.stopBox}>
      <div className={s.stopStack}>
        <div className={s.stopConfirmTitle}>Killed · the run ends with no saved stats</div>
        <div className={s.stopNote}>
          The log and last heartbeat are kept as evidence for triage.
        </div>
        <Button tone="ghost" size="lg" onClick={() => onStage('idle')}>Done</Button>
      </div>
    </div>
  );
}
