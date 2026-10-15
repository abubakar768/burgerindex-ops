'use client';

// The API has no login endpoint: every route takes `Authorization: Bearer <API_TOKEN>`.
// The operator name is sent as `user` on Stop / Run / autofix / Approve, which the
// backend writes to AUDIT_LOG, so both are collected once and kept in localStorage.

const TOKEN_KEY = 'bi-ops.token';
const USER_KEY = 'bi-ops.user';
const BASE_KEY = 'bi-ops.base';

export interface Session {
  token: string;
  user: string;
  /** Empty means same origin: the FastAPI app serves this page. */
  base: string;
}

export const EMPTY_SESSION: Session = { token: '', user: '', base: '' };

export function readSession(): Session {
  if (typeof window === 'undefined') return EMPTY_SESSION;
  try {
    return {
      token: window.localStorage.getItem(TOKEN_KEY) ?? '',
      user: window.localStorage.getItem(USER_KEY) ?? '',
      base: (window.localStorage.getItem(BASE_KEY) ?? '').replace(/\/$/, ''),
    };
  } catch {
    return EMPTY_SESSION;
  }
}

export function writeSession(next: Session): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, next.token);
    window.localStorage.setItem(USER_KEY, next.user);
    window.localStorage.setItem(BASE_KEY, next.base.replace(/\/$/, ''));
  } catch {
    /* private mode: the session simply does not persist */
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export function isSignedIn(s: Session): boolean {
  return Boolean(s.token && s.user);
}

/**
 * The module-level session the API client reads. Kept in sync by SessionProvider
 * so request helpers stay plain functions rather than hooks.
 */
let active: Session = EMPTY_SESSION;

export function setActiveSession(s: Session): void {
  active = s;
}

export function getActiveSession(): Session {
  return active;
}
