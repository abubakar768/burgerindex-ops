'use client';

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react';
import {
  EMPTY_SESSION, clearSession, isSignedIn, readSession, setActiveSession, writeSession,
  type Session,
} from '@/lib/session';
import { cx } from './Primitives';
import s from './ui.module.css';

/* --------------------------------------------------------------- session -- */

interface SessionContextValue {
  session: Session;
  ready: boolean;
  signIn: (next: Session) => void;
  signOut: () => void;
}

const SessionContext = createContext<SessionContextValue>({
  session: EMPTY_SESSION,
  ready: false,
  signIn: () => {},
  signOut: () => {},
});

export function useSession(): SessionContextValue {
  return useContext(SessionContext);
}

/* ---------------------------------------------------------------- toasts -- */

export type ToastKind = 'ok' | 'err' | 'info';

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const ToastContext = createContext<(message: string, kind?: ToastKind) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

/* -------------------------------------------------------------- provider -- */

export function Providers({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>(EMPTY_SESSION);
  const [ready, setReady] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  // localStorage is only available after mount, so the first paint is neutral.
  useEffect(() => {
    const stored = readSession();
    setActiveSession(stored);
    setSession(stored);
    setReady(true);
  }, []);

  const signIn = useCallback((next: Session) => {
    writeSession(next);
    setActiveSession(next);
    setSession(next);
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    const next = { ...EMPTY_SESSION, base: session.base };
    setActiveSession(next);
    setSession(next);
  }, [session.base]);

  const pushToast = useCallback((message: string, kind: ToastKind = 'err') => {
    seq.current += 1;
    const id = seq.current;
    setToasts((list) => [...list, { id, kind, message }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 6000);
  }, []);

  const sessionValue = useMemo(
    () => ({ session, ready, signIn, signOut }),
    [session, ready, signIn, signOut],
  );

  return (
    <SessionContext.Provider value={sessionValue}>
      <ToastContext.Provider value={pushToast}>
        {children}
        <div className={s.toasts} aria-live="polite">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={cx(s.toast, t.kind === 'err' && s.toastErr, t.kind === 'ok' && s.toastOk)}
            >
              {t.message}
            </div>
          ))}
        </div>
      </ToastContext.Provider>
    </SessionContext.Provider>
  );
}

export { isSignedIn };
