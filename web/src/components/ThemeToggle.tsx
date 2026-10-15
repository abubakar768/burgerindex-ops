'use client';

import { useTheme } from './Providers';
import { Icon } from './Primitives';
import s from './ui.module.css';

/** Switches between the design's dark palette and the light one. */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const goingLight = theme === 'dark';

  return (
    <button
      type="button"
      className={s.themeToggle}
      onClick={toggleTheme}
      aria-pressed={theme === 'light'}
      title={goingLight ? 'Switch to the light theme' : 'Switch to the dark theme'}
    >
      <Icon name={goingLight ? 'sun' : 'moon'} size={15} width={1.8} />
      {goingLight ? 'Light' : 'Dark'}
    </button>
  );
}
