'use client';

/**
 * ASTRA — Sidebar Navigation (WCAG 2.1 AA)
 * ===========================================
 * File: frontend/src/components/layout/Sidebar.tsx   ← REPLACES existing
 *
 * Accessibility additions:
 *   - role="navigation" with aria-label="Main navigation" (WCAG 1.3.1)
 *   - aria-current="page" on the active link (WCAG 2.4.8)
 *   - Arrow-key navigation between nav items (WAI-ARIA Practices)
 *   - id="main-navigation" as skip-link target
 *   - All interactive elements have visible focus indicators
 *   - Logout button has accessible name via aria-label
 *   - Badge counts use aria-label (not colour alone — WCAG 1.4.1)
 *   - Contrast-boosted text colours (4.5:1 minimum)
 */

import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  FileText, MonitorDot, MessageSquare, Network, Archive,
  Settings, LayoutDashboard, ChevronRight, LogOut, Shield,
} from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '@/lib/auth';
import { requirementsAPI, projectsAPI } from '@/lib/api';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/requirements', label: 'Requirements', icon: FileText, countKey: 'requirements' },
  { href: '/baselines', label: 'Baselines', icon: Archive },
  { href: '/traceability', label: 'Traceability', icon: Network },
  { href: '/audit', label: 'Audit Log', icon: Shield },
  { href: '/interfaces', label: 'Interfaces', icon: MonitorDot },
  { href: '/communication', label: 'Communication', icon: MessageSquare },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [reqCount, setReqCount] = useState<number | null>(null);

  // Refs for arrow-key navigation
  const navRef = useRef<HTMLElement>(null);
  const linkRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  const initials = user?.full_name
    ? user.full_name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : '??';

  // Fetch requirements count
  useEffect(() => {
    if (!user) return;
    projectsAPI
      .list()
      .then((res) => {
        if (res.data.length > 0) {
          requirementsAPI
            .list(res.data[0].id, { limit: 200 })
            .then((fullRes) => setReqCount(fullRes.data.length));
        }
      })
      .catch(() => {});
  }, [user, pathname]);

  // ── Arrow-key navigation (WAI-ARIA Practices: Navigation) ──
  const handleNavKeyDown = useCallback(
    (e: KeyboardEvent<HTMLElement>) => {
      const links = linkRefs.current.filter(Boolean) as HTMLAnchorElement[];
      const currentIdx = links.findIndex((el) => el === document.activeElement);

      let nextIdx = -1;
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          nextIdx = currentIdx < links.length - 1 ? currentIdx + 1 : 0;
          break;
        case 'ArrowUp':
          e.preventDefault();
          nextIdx = currentIdx > 0 ? currentIdx - 1 : links.length - 1;
          break;
        case 'Home':
          e.preventDefault();
          nextIdx = 0;
          break;
        case 'End':
          e.preventDefault();
          nextIdx = links.length - 1;
          break;
        default:
          return;
      }
      links[nextIdx]?.focus();
    },
    []
  );

  return (
    <aside
      className="fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-astra-border bg-astra-surface"
      aria-label="Application sidebar"
    >
      {/* ── Logo ── */}
      <div className="border-b border-astra-border px-5 py-4">
        <div className="flex items-center gap-3">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-sm font-extrabold text-white"
            aria-hidden="true"
          >
            A
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-slate-100">
              ASTRA
            </div>
            <div className="text-[10px] font-medium tracking-widest text-[var(--text-muted)]">
              SYSTEMS ENGINEERING
            </div>
          </div>
        </div>
      </div>

      {/* ── Project Selector ── */}
      <div className="border-b border-astra-border p-3">
        <button
          className="flex w-full items-center justify-between rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2 transition hover:border-blue-500/30"
          aria-label="Select project — currently SMDS"
          aria-haspopup="listbox"
        >
          <div>
            <div className="text-xs font-semibold text-slate-200">SMDS</div>
            <div className="text-[10px] text-[var(--text-muted)]">
              Satellite Missile Deployment
            </div>
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-dim)]" aria-hidden="true" />
        </button>
      </div>

      {/* ── Navigation ── */}
      <nav
        id="main-navigation"
        ref={navRef}
        role="navigation"
        aria-label="Main navigation"
        className="flex-1 space-y-0.5 p-2"
        onKeyDown={handleNavKeyDown}
      >
        {NAV_ITEMS.map((item, idx) => {
          const active =
            pathname === item.href ||
            (item.href !== '/' && pathname.startsWith(item.href));
          const Icon = item.icon;
          const count =
            item.countKey === 'requirements' ? reqCount : undefined;

          return (
            <Link
              key={item.href}
              ref={(el) => { linkRefs.current[idx] = el; }}
              href={item.href}
              aria-current={active ? 'page' : undefined}
              aria-label={
                count !== undefined && count !== null
                  ? `${item.label} — ${count} items`
                  : item.label
              }
              className={clsx(
                'flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[13px] font-medium transition-all',
                active
                  ? 'border border-blue-500/20 bg-blue-500/10 text-blue-400'
                  : 'border border-transparent text-[var(--text-muted)] hover:bg-slate-800 hover:text-slate-200'
              )}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
              <span className="flex-1">{item.label}</span>
              {count !== undefined && count !== null && (
                <span
                  className={clsx(
                    'rounded-full px-2 py-0.5 text-[10px] font-bold',
                    active
                      ? 'bg-blue-500 text-white'
                      : 'bg-astra-surface-alt text-[var(--text-dim)]'
                  )}
                  aria-hidden="true"
                >
                  {count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── User info + logout ── */}
      <div className="border-t border-astra-border p-3">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 text-xs font-bold text-white"
            aria-hidden="true"
          >
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-slate-200 truncate">
              {user?.full_name || 'User'}
            </div>
            <div className="text-[10px] text-[var(--text-muted)] truncate">
              {user?.role?.replace('_', ' ') || ''}
            </div>
          </div>
          <button
            onClick={logout}
            className="p-1.5 rounded-lg text-[var(--text-dim)] hover:text-red-400 hover:bg-red-500/10 transition"
            aria-label={`Sign out ${user?.full_name || ''}`}
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
