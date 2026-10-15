'use client';

// The design canvas is dark, so dark stays the default. A viewer can switch to
// light and the choice sticks in this browser.

export type Theme = 'dark' | 'light';

export const THEME_KEY = 'bi-ops.theme';
export const DEFAULT_THEME: Theme = 'dark';

export function readTheme(): Theme {
  if (typeof window === 'undefined') return DEFAULT_THEME;
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === 'light' || stored === 'dark' ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
}

export function writeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode: the choice just does not persist */
  }
}

/**
 * Runs before first paint, inlined in <head>, so a light-theme viewer never sees
 * a dark flash. Kept tiny and dependency-free on purpose.
 */
export const NO_FLASH_SCRIPT = `(function(){try{var t=localStorage.getItem('${THEME_KEY}');document.documentElement.setAttribute('data-theme',t==='light'?'light':'dark')}catch(e){document.documentElement.setAttribute('data-theme','dark')}})()`;
