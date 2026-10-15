'use client';

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react';
import {
  EMPTY_SESSION, clearSession, isSignedIn, readSession, setActiveSession, writeSession,
  type Session,
} from '@/lib/session';
import { DEFAULT_THEME, applyTheme, readTheme, writeTheme, type Theme } from '@/lib/theme';
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

/* ----------------------------------------------------------------- theme -- */

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  toggleTheme: () => {},
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
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
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME);
  const seq = useRef(0);

  // localStorage is only available after mount, so the first paint is neutral.
  useEffect(() => {
    const stored = readSession();
    setActiveSession(stored);
    setSession(stored);
    setReady(true);
    // The inline script in <head> already set the attribute; this syncs React
    // to whatever it chose, so the toggle starts on the right label.
    setTheme(readTheme());
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      writeTheme(next);
      return next;
    });
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

  const themeValue = useMemo(() => ({ theme, toggleTheme }), [theme, toggleTheme]);

  return (
    <SessionContext.Provider value={sessionValue}>
      <ThemeContext.Provider value={themeValue}>
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
      </ThemeContext.Provider>
    </SessionContext.Provider>
  );
}

export { isSignedIn };
