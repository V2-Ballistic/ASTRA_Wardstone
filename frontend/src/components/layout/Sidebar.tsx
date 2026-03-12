'use client';

/**
 * ASTRA — Sidebar Navigation (Project-Scoped, WCAG 2.1 AA)
 * ===========================================================
 * File: frontend/src/components/layout/Sidebar.tsx
 *
 * Two-level navigation:
 *   Global (/ route) → project list, account, admin
 *   Project (/projects/[id]/*) → engineering, management, AI, admin sections
 *
 * Accessibility:
 *   - role="navigation" with aria-label (WCAG 1.3.1)
 *   - aria-current="page" on active link (WCAG 2.4.8)
 *   - Arrow-key navigation between nav items
 *   - All interactive elements have visible focus indicators
 *   - Badge counts use aria-label (not colour alone — WCAG 1.4.1)
 *   - Contrast-boosted text colours (4.5:1 minimum)
 */

import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  FileText, Network, Archive, Settings, LayoutDashboard,
  ChevronDown, ChevronRight, LogOut, Shield, FolderOpen,
  Sparkles, Search, Zap, CheckSquare, FileBarChart,
  Users, Home, ChevronLeft, Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '@/lib/auth';
import { projectsAPI, requirementsAPI } from '@/lib/api';

// ══════════════════════════════════════
//  Types
// ══════════════════════════════════════

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  countKey?: string;
  roles?: string[];  // If set, only show for these roles
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

interface ProjectInfo {
  id: number;
  code: string;
  name: string;
  description?: string;
}

// ══════════════════════════════════════
//  Navigation Definitions
// ══════════════════════════════════════

const GLOBAL_NAV: NavItem[] = [
  { href: '/', label: 'Projects', icon: Home },
];

function getProjectNav(projectId: number): NavGroup[] {
  const p = `/projects/${projectId}`;
  return [
    {
      title: 'ENGINEERING',
      items: [
        { href: p, label: 'Dashboard', icon: LayoutDashboard },
        { href: `${p}/requirements`, label: 'Requirements', icon: FileText, countKey: 'requirements' },
        { href: `${p}/traceability`, label: 'Traceability', icon: Network },
        { href: `${p}/verification`, label: 'Verification', icon: CheckSquare },
      ],
    },
    {
      title: 'MANAGEMENT',
      items: [
        { href: `${p}/baselines`, label: 'Baselines', icon: Archive },
        { href: `${p}/reports`, label: 'Reports', icon: FileBarChart },
      ],
    },
    {
      title: 'AI TOOLS',
      items: [
        { href: `${p}/ai`, label: 'AI Assistant', icon: Sparkles },
        { href: `${p}/impact`, label: 'Impact Analysis', icon: Zap },
      ],
    },
    {
      title: 'ADMIN',
      items: [
        { href: `${p}/audit`, label: 'Audit Log', icon: Shield, roles: ['admin', 'project_manager'] },
        { href: `${p}/settings`, label: 'Settings', icon: Settings },
      ],
    },
  ];
}

// ══════════════════════════════════════
//  Helper: extract projectId from pathname
// ══════════════════════════════════════

function extractProjectId(pathname: string): number | null {
  const match = pathname.match(/^\/projects\/(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

// ══════════════════════════════════════
//  Project Switcher Dropdown
// ══════════════════════════════════════

function ProjectSwitcher({
  current,
  projects,
  loading,
  onSelect,
}: {
  current: ProjectInfo | null;
  projects: ProjectInfo[];
  loading: boolean;
  onSelect: (p: ProjectInfo) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (loading || !current) {
    return (
      <div className="border-b border-astra-border p-3">
        <div className="flex items-center gap-2 rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-500" />
          <span className="text-xs text-slate-500">Loading projects…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="border-b border-astra-border p-3" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2 transition hover:border-blue-500/30"
        aria-label={`Current project: ${current.name}. Click to switch.`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-slate-200 truncate">{current.code}</div>
          <div className="text-[10px] text-[var(--text-muted)] truncate">{current.name}</div>
        </div>
        <ChevronDown
          className={clsx(
            'h-3.5 w-3.5 text-[var(--text-dim)] transition-transform',
            open && 'rotate-180'
          )}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          className="mt-1.5 max-h-52 overflow-y-auto rounded-lg border border-astra-border bg-astra-surface shadow-xl"
          role="listbox"
          aria-label="Switch project"
        >
          {projects.map((p) => (
            <button
              key={p.id}
              role="option"
              aria-selected={p.id === current.id}
              onClick={() => {
                onSelect(p);
                setOpen(false);
              }}
              className={clsx(
                'flex w-full items-center gap-2.5 px-3 py-2 text-left transition',
                p.id === current.id
                  ? 'bg-blue-500/10 text-blue-400'
                  : 'text-slate-300 hover:bg-astra-surface-hover'
              )}
            >
              <FolderOpen className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold truncate">{p.code}</div>
                <div className="text-[10px] text-[var(--text-dim)] truncate">{p.name}</div>
              </div>
              {p.id === current.id && (
                <div className="h-1.5 w-1.5 rounded-full bg-blue-400" aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════
//  Main Sidebar Component
// ══════════════════════════════════════

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  // ── State ──
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [reqCount, setReqCount] = useState<number | null>(null);

  // ── Refs for arrow-key nav ──
  const navRef = useRef<HTMLElement>(null);
  const linkRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  // ── Derive context from URL ──
  const currentProjectId = extractProjectId(pathname);
  const isInProject = currentProjectId !== null;
  const currentProject = projects.find((p) => p.id === currentProjectId) || null;

  // ── Fetch projects ──
  useEffect(() => {
    if (!user) return;
    setProjectsLoading(true);
    projectsAPI
      .list()
      .then((res) => setProjects(res.data || []))
      .catch(() => {})
      .finally(() => setProjectsLoading(false));
  }, [user]);

  // ── Fetch requirement count for current project ──
  useEffect(() => {
    if (!currentProjectId) {
      setReqCount(null);
      return;
    }
    requirementsAPI
      .list(currentProjectId, { limit: 1000 })
      .then((res) => setReqCount(Array.isArray(res.data) ? res.data.length : 0))
      .catch(() => setReqCount(null));
  }, [currentProjectId, pathname]);

  // ── Initials ──
  const initials = user?.full_name
    ? user.full_name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : '??';

  // ── Arrow-key navigation ──
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

  // ── Project switch handler ──
  const handleProjectSwitch = (project: ProjectInfo) => {
    router.push(`/projects/${project.id}`);
  };

  // ── Build flat link list for arrow-key indexing ──
  let linkIndex = 0;

  // ── Check if a nav link is active ──
  const isActive = (href: string) => {
    if (!isInProject) {
      return pathname === href;
    }
    // Exact match for dashboard (e.g., /projects/1)
    if (href === `/projects/${currentProjectId}`) {
      return pathname === href;
    }
    // Prefix match for sub-pages
    return pathname.startsWith(href);
  };

  // ── Render a single nav link ──
  const renderNavLink = (item: NavItem) => {
    // Role filtering
    if (item.roles && user?.role && !item.roles.includes(user.role)) {
      return null;
    }

    const active = isActive(item.href);
    const Icon = item.icon;
    const count = item.countKey === 'requirements' ? reqCount : undefined;
    const idx = linkIndex++;

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
          'flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-all',
          active
            ? 'border border-blue-500/20 bg-blue-500/10 text-blue-400'
            : 'border border-transparent text-[var(--text-muted)] hover:bg-slate-800 hover:text-slate-200'
        )}
      >
        <Icon className="h-[18px] w-[18px] flex-shrink-0" aria-hidden="true" />
        <span className="flex-1 truncate">{item.label}</span>
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
  };

  // ══════════════════════════════════════
  //  Render
  // ══════════════════════════════════════

  // Reset link index on each render
  linkIndex = 0;

  return (
    <aside
      className="fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-astra-border bg-astra-surface"
      aria-label="Application sidebar"
    >
      {/* ── Logo ── */}
      <div className="border-b border-astra-border px-5 py-4">
        <Link href="/" className="flex items-center gap-3 group">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-sm font-extrabold text-white transition-transform group-hover:scale-105"
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
        </Link>
      </div>

      {/* ── Project Context Area ── */}
      {isInProject ? (
        <>
          {/* Back to all projects */}
          <div className="border-b border-astra-border px-3 pt-2 pb-1">
            <Link
              href="/"
              className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium text-[var(--text-dim)] transition hover:text-slate-200 hover:bg-slate-800"
            >
              <ChevronLeft className="h-3 w-3" aria-hidden="true" />
              All Projects
            </Link>
          </div>

          {/* Project switcher */}
          <ProjectSwitcher
            current={currentProject}
            projects={projects}
            loading={projectsLoading}
            onSelect={handleProjectSwitch}
          />
        </>
      ) : (
        /* Global: show recent projects below logo */
        projects.length > 0 && (
          <div className="border-b border-astra-border p-3">
            <div className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-dim)]">
              Recent Projects
            </div>
            <div className="space-y-0.5">
              {projects.slice(0, 5).map((p) => (
                <Link
                  key={p.id}
                  href={`/projects/${p.id}`}
                  className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[12px] text-[var(--text-muted)] transition hover:bg-slate-800 hover:text-slate-200"
                >
                  <FolderOpen className="h-3.5 w-3.5 flex-shrink-0 text-[var(--text-dim)]" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <span className="font-semibold">{p.code}</span>
                    <span className="text-[var(--text-dim)]"> · {p.name}</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )
      )}

      {/* ── Navigation ── */}
      <nav
        id="main-navigation"
        ref={navRef}
        role="navigation"
        aria-label={isInProject ? 'Project navigation' : 'Main navigation'}
        className="flex-1 overflow-y-auto p-2"
        onKeyDown={handleNavKeyDown}
      >
        {isInProject && currentProjectId ? (
          /* ── PROJECT-SCOPED NAV ── */
          <div className="space-y-4">
            {getProjectNav(currentProjectId).map((group) => {
              const visibleItems = group.items.filter(
                (item) => !item.roles || !user?.role || item.roles.includes(user.role)
              );
              if (visibleItems.length === 0) return null;

              return (
                <div key={group.title}>
                  <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-dim)]">
                    {group.title}
                  </div>
                  <div className="space-y-0.5">
                    {visibleItems.map((item) => renderNavLink(item))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* ── GLOBAL NAV ── */
          <div className="space-y-0.5">
            {GLOBAL_NAV.map((item) => renderNavLink(item))}
          </div>
        )}
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
