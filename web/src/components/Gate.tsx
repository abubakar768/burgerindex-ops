'use client';

import { useState, type FormEvent } from 'react';
import { api } from '@/lib/api';
import { setActiveSession } from '@/lib/session';
import { useSession } from './Providers';
import { Button } from './Primitives';
import s from './ui.module.css';

/**
 * The API has no login route: it checks `Authorization: Bearer <API_TOKEN>` on
 * every request. So this collects the token once, plus the operator name the
 * backend records in AUDIT_LOG for Stop / Run / autofix / Approve.
 */
export function Gate() {
  const { session, signIn } = useSession();
  const [token, setToken] = useState('');
  const [user, setUser] = useState('');
  const [base, setBase] = useState(session.base);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!token.trim() || !user.trim()) {
      setError('Both the API token and your name are required.');
      return;
    }

    setChecking(true);
    const candidate = { token: token.trim(), user: user.trim(), base: base.trim() };
    setActiveSession(candidate);

    try {
      // /spiders is the cheapest authenticated route, so it doubles as the check.
      await api.spiders();
      signIn(candidate);
    } catch (cause) {
      const status = (cause as { status?: number }).status;
      setError(
        status === 401
          ? 'That token was rejected. It must match API_TOKEN in the ops .env.'
          : status === 0
            ? 'Could not reach the API. Check that uvicorn is running and the base URL is right.'
            : `Sign-in failed: ${(cause as Error).message}`,
      );
      setChecking(false);
    }
  }

  return (
    <div className={s.gate}>
      <form className={s.gateCard} onSubmit={onSubmit}>
        <div>
          <div className={s.eyebrow}>BURGERINDEX-OPS</div>
          <h1 className={s.title} style={{ fontSize: 24, lineHeight: '32px', marginTop: 6 }}>
            Crawler operations
          </h1>
        </div>

        <div className={s.gateField}>
          <label htmlFor="gate-token">API token</label>
          <input
            id="gate-token"
            className={s.input}
            type="password"
            value={token}
            autoComplete="off"
            onChange={(e) => setToken(e.target.value)}
            placeholder="API_TOKEN"
          />
          <div className={s.gateHint}>
            The value of <code>API_TOKEN</code> in the ops <code>.env</code>. Stored in this
            browser only, and sent as a bearer token.
          </div>
        </div>

        <div className={s.gateField}>
          <label htmlFor="gate-user">Your name</label>
          <input
            id="gate-user"
            className={s.input}
            type="text"
            value={user}
            autoComplete="username"
            onChange={(e) => setUser(e.target.value)}
            placeholder="abubakar"
          />
          <div className={s.gateHint}>
            Recorded in the audit log against every Stop, Run and Approve you make.
          </div>
        </div>

        <div className={s.gateField}>
          <label htmlFor="gate-base">API base URL</label>
          <input
            id="gate-base"
            className={s.input}
            type="text"
            value={base}
            onChange={(e) => setBase(e.target.value)}
            placeholder="leave empty for this origin"
          />
          <div className={s.gateHint}>
            Empty means the API that served this page. Set it only when running the
            Next.js dev server separately, e.g. <code>http://localhost:8090</code>.
          </div>
        </div>

        {error ? <div className={s.gateErr}>{error}</div> : null}

        <Button type="submit" tone="primary" size="xl" block disabled={checking}>
          {checking ? 'Checking…' : 'Continue'}
        </Button>
      </form>
    </div>
  );
}
