'use client';

import type { ReactNode } from 'react';
import { isSignedIn, useSession } from './Providers';
import { Gate } from './Gate';
import { Sidebar } from './Sidebar';
import shell from './Sidebar.module.css';
import s from './ui.module.css';

/**
 * Every page is behind the token gate. Until localStorage has been read the
 * shell renders nothing, so a signed-in operator never sees the gate flash.
 *
 * Signed in, the layout is a fixed left sidebar plus the scrolling page. The
 * sidebar owns navigation, the signed-in identity and the theme toggle, so page
 * headers carry only what belongs to that page -- its filters and actions.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { session, ready } = useSession();

  if (!ready) return <div className={s.page} />;
  if (!isSignedIn(session)) return <Gate />;

  return (
    <div className={shell.shell}>
      <a href="#content" className="skipLink">Skip to content</a>
      <Sidebar />
      <main id="content" tabIndex={-1} className={shell.main}>
        <div className={s.page}>{children}</div>
      </main>
    </div>
  );
}
