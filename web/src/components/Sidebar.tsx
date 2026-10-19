'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { useSession } from './Providers';
import { ThemeToggle } from './ThemeToggle';
import { Icon, cx, type IconName } from './Primitives';
import s from './Sidebar.module.css';

const BADGE_REFRESH_MS = 60_000;

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  /** Child routes that should light this item up. */
  owns?: string[];
}

const ITEMS: NavItem[] = [
  { href: '/live', label: 'Live crawlers', icon: 'activity' },
  { href: '/schedules', label: 'Schedules', icon: 'calendar' },
  // Fix review is reached from an issue, so it keeps Issues lit.
  { href: '/issues', label: 'Issues', icon: 'warnTriangle', owns: ['/fix'] },
];

export function Sidebar() {
  const pathname = usePathname();
  const { session, signOut } = useSession();

  // At-a-glance counts, so you can see from any page whether anything needs
  // you. Both endpoints are cheap; a failure just leaves the badge off.
  const crawlers = usePoll((signal) => api.crawlers(signal), BADGE_REFRESH_MS);
  const issues = usePoll((signal) => api.issues(7, signal), BADGE_REFRESH_MS);

  const counts: Record<string, { value: number; hot: boolean } | undefined> = {
    '/live': crawlers.data ? { value: crawlers.data.length, hot: false } : undefined,
    '/issues': issues.data
      ? { value: issues.data.length, hot: issues.data.some((r) => r.p0) }
      : undefined,
  };

  return (
    <aside className={s.sidebar}>
      <div className={s.brand}>
        <span className={s.brandName}>burgerindex ops</span>
        <span className={s.brandSub}>CRAWLER CONTROL</span>
      </div>

      <nav className={s.nav} aria-label="Sections">
        {ITEMS.map((item) => {
          const active = isActive(pathname, item);
          const badge = counts[item.href];
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cx(s.navLink, active && s.navLinkActive)}
              aria-current={active ? 'page' : undefined}
            >
              <Icon name={item.icon} size={17} width={1.8} />
              {item.label}
              {badge ? (
                <span className={cx(s.navBadge, badge.hot && s.navBadgeHot)}>
                  {badge.value}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>

      <div className={s.foot}>
        <div className={s.who}>
          Signed in as <span className={s.whoName}>{session.user}</span>
          <span className={s.whoApi}>{session.base || 'API on this origin'}</span>
        </div>
        <div className={s.footRow}>
          <ThemeToggle />
          <button type="button" className={s.signOut} onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    </aside>
  );
}

/** Trailing slashes are on, so compare prefixes rather than exact strings. */
function isActive(pathname: string | null, item: NavItem): boolean {
  if (!pathname) return false;
  const here = pathname.replace(/\/$/, '') || '/';
  if (here === item.href) return true;
  return (item.owns ?? []).some((owned) => here === owned || here.startsWith(`${owned}/`));
}
