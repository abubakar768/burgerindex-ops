'use client';

import type { ReactNode } from 'react';
import { isSignedIn, useSession } from './Providers';
import { Gate } from './Gate';
import s from './ui.module.css';

/**
 * Every page is behind the token gate. Until localStorage has been read the
 * shell renders nothing, so a signed-in operator never sees the gate flash.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { session, ready, signOut } = useSession();

  if (!ready) return <div className={s.page} />;
  if (!isSignedIn(session)) return <Gate />;

  return (
    <div className={s.page}>
      {children}
      <footer className={s.appFooter}>
        <span>
          Signed in as <strong>{session.user}</strong>
          {session.base ? ` · API ${session.base}` : ' · API on this origin'}
        </span>
        <button type="button" className={s.linkBtn} onClick={signOut}>
          Sign out
        </button>
      </footer>
    </div>
  );
}
