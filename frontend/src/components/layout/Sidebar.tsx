'use client';

/**
 * ASTRA — Sidebar Navigation (with Auto-Req Toggle Support)
 * ============================================================
 * File: frontend/src/components/layout/Sidebar.tsx
 *
 * Changes from original:
 *   - Fetches project.auto_req_approval_required on project change
 *   - Conditionally shows/hides "Auto Requirements" nav item
 *   - Shows pending count badge on Auto Requirements when visible
 */

import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  FileText, Network, Archive, Settings, LayoutDashboard,
  ChevronDown, ChevronRight, LogOut, Shield, FolderOpen,
  Sparkles, Search, Zap, CheckSquare, FileBarChart, Upload,
  Users, Home, ChevronLeft, Loader2, Cable, Package, RefreshCw,
  ShieldCheck, Boxes, Wrench, CircuitBoard,
} from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '@/lib/auth';
import { projectsAPI, dashboardAPI } from '@/lib/api';
import { reqSyncAPI } from '@/lib/req-sync-api';
import { coverageAPI } from '@/lib/coverage-api';

// ══════════════════════════════════════
//  Types
// ══════════════════════════════════════

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  countKey?: string;
  roles?: string[];
  conditionalKey?: string; // NEW: key to check in project data for visibility
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
  auto_req_approval_required?: boolean;
}

// ══════════════════════════════════════
//  Navigation Definitions
// ══════════════════════════════════════

const GLOBAL_NAV: NavItem[] = [
  { href: '/', label: 'Projects', icon: Home },
  // Phase 3 — INTF-002: global supplier catalog landing.
  { href: '/catalog', label: 'Catalog', icon: Package },
  // CLEANUP-002 Phase 3: Parts Library entry removed from sidebar.
  // The /parts-library/* routes 308-redirect to /catalog/* equivalents
  // (next.config.js) so existing bookmarks survive. Underlying route
  // tree under frontend/src/app/parts-library/ is left in place per
  // AD-4 / out-of-scope rule #1; sunsetting it is a future TDD.
];

function getProjectNav(projectId: number): NavGroup[] {
  const p = `/projects/${projectId}`;
  return [
    {
      title: 'ENGINEERING',
      items: [
        { href: p, label: 'Dashboard', icon: LayoutDashboard },
        { href: `${p}/requirements`, label: 'Requirements', icon: FileText, countKey: 'requirements' },
        { href: `${p}/artifacts`, label: 'Source Artifacts', icon: FolderOpen },
        { href: `${p}/traceability`, label: 'Traceability', icon: Network },
        { href: `${p}/verification`, label: 'Verification', icon: CheckSquare },
        // ASTRA-SPEC-PARTS-001 §5.4: nav restructure. Order matters.
        { href: `${p}/system-architecture`, label: 'System Architecture', icon: CircuitBoard },
        { href: `${p}/parts`, label: 'Parts', icon: Boxes },
        // Label changed to ELECTRICAL INTERFACES; route unchanged for
        // backward compatibility with existing bookmarks / API contracts.
        { href: `${p}/interfaces`, label: 'Electrical Interfaces', icon: Cable },
        { href: `${p}/mechanical-interfaces`, label: 'Mechanical Interfaces', icon: Wrench },
      ],
    },
    {
      title: 'MANAGEMENT',
      items: [
        { href: `${p}/baselines`, label: 'Baselines', icon: Archive },
        { href: `${p}/reports`, label: 'Reports', icon: FileBarChart },
        { href: `${p}/import`, label: 'Import', icon: Upload },
        // Phase 6 — INTF-002 Source Coverage dashboard. Badge = total
        // warning + error orphans across all levels.
        {
          href: `${p}/coverage`,
          label: 'Coverage',
          icon: ShieldCheck,
          countKey: 'coverage_issues',
        },
      ],
    },
    {
      title: 'AI TOOLS',
      items: [
        { href: `${p}/ai`, label: 'AI Assistant', icon: Sparkles },
        { href: `${p}/impact`, label: 'Impact Analysis', icon: Zap },
        {
          href: `${p}/interfaces/auto-requirements`,
          label: 'Auto Requirements',
          icon: Sparkles,
          conditionalKey: 'auto_req_approval_required', // Only show when this is true
        },
        // Phase 5 — INTF-002 Reactive Requirement Sync
        {
          href: `${p}/req-sync`,
          label: 'Sync Proposals',
          icon: RefreshCw,
          countKey: 'sync_proposals',
        },
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
  return match ? parseInt(match[1]) : null;
}

// ══════════════════════════════════════
//  Sidebar Component
// ══════════════════════════════════════

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const projectId = extractProjectId(pathname);

  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set(['ENGINEERING', 'MANAGEMENT', 'AI TOOLS', 'ADMIN']));

  // ── Fetch project info (includes auto_req_approval_required) ──
  useEffect(() => {
    if (projectId) {
      projectsAPI.get(projectId).then(r => {
        setProject(r.data);
      }).catch(() => setProject(null));

      // F-026: pull the requirement count from /dashboard/stats — the
      // GROUP BY total there is a single COUNT(*) query against the DB.
      // Pre-fix this called requirementsAPI.list(limit: 1) and counted
      // r.data.length, which always returned ≤ 1 — the sidebar badge
      // never reflected the real count, just whether ≥1 requirement
      // existed.
      dashboardAPI.getStats(projectId).then(r => {
        setCounts(prev => ({
          ...prev,
          requirements: Number(r.data?.total_requirements ?? 0),
        }));
      }).catch(() => {});

      // Phase 5 — pending sync proposal count for the sidebar badge.
      reqSyncAPI.pendingCount(projectId).then(n => {
        setCounts(prev => ({ ...prev, sync_proposals: n }));
      }).catch(() => {});

      // Phase 6 — coverage badge: warning + error orphans across all levels.
      coverageAPI.badgeCount(projectId).then(n => {
        setCounts(prev => ({ ...prev, coverage_issues: n }));
      }).catch(() => {});
    } else {
      setProject(null);
      setCounts({});
    }
  }, [projectId]);

  const toggleGroup = (title: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      next.has(title) ? next.delete(title) : next.add(title);
      return next;
    });
  };

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  const isActive = (href: string) => {
    if (href === '/' && pathname === '/') return true;
    if (href === '/' && pathname !== '/') return false;
    if (projectId && href === `/projects/${projectId}`) return pathname === href;
    return pathname.startsWith(href) && href !== `/projects/${projectId}`;
  };

  // ── Filter nav items based on role and conditional visibility ──
  const shouldShowItem = (item: NavItem): boolean => {
    // Role check
    if (item.roles && user && !item.roles.includes(user.role)) return false;

    // Conditional visibility check (for auto-requirements toggle)
    if (item.conditionalKey && project) {
      const value = (project as any)[item.conditionalKey];
      // If the key exists and is explicitly false, hide the item
      if (value === false) return false;
    }

    return true;
  };

  const navGroups = projectId ? getProjectNav(projectId) : [];

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 left-0 z-30 flex flex-col border-r border-astra-border bg-astra-surface transition-all duration-200',
        collapsed ? 'w-16' : 'w-60'
      )}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between border-b border-astra-border px-4">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 text-xs font-extrabold text-white">
              A
            </div>
            <span className="text-sm font-bold text-slate-200 tracking-tight">ASTRA</span>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="rounded-lg p-1.5 text-slate-500 hover:text-slate-300 hover:bg-astra-surface-alt transition"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ChevronLeft className={clsx('h-4 w-4 transition-transform', collapsed && 'rotate-180')} />
        </button>
      </div>

      {/* Project info */}
      {project && !collapsed && (
        <div className="border-b border-astra-border px-4 py-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Project</div>
          <div className="text-sm font-semibold text-slate-200 truncate">{project.name}</div>
          <div className="text-[10px] font-mono text-slate-500">{project.code}</div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {/* Global nav */}
        {GLOBAL_NAV.map(item => (
          <Link key={item.href} href={item.href}
            className={clsx(
              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition mb-1',
              isActive(item.href) ? 'bg-blue-500/15 text-blue-400' : 'text-slate-400 hover:text-slate-200 hover:bg-astra-surface-alt'
            )}>
            <item.icon className="h-4 w-4 flex-shrink-0" />
            {!collapsed && <span>{item.label}</span>}
          </Link>
        ))}

        {/* Project nav groups */}
        {navGroups.map(group => {
          const visibleItems = group.items.filter(shouldShowItem);
          if (visibleItems.length === 0) return null;

          const isExpanded = expandedGroups.has(group.title);
          return (
            <div key={group.title} className="mt-3">
              {!collapsed && (
                <button
                  onClick={() => toggleGroup(group.title)}
                  className="flex w-full items-center justify-between px-3 py-1.5 text-[9px] font-bold uppercase tracking-widest text-slate-600 hover:text-slate-400"
                >
                  {group.title}
                  {isExpanded
                    ? <ChevronDown className="h-3 w-3" />
                    : <ChevronRight className="h-3 w-3" />}
                </button>
              )}

              {(isExpanded || collapsed) && visibleItems.map(item => {
                const active = isActive(item.href);
                const count = item.countKey ? counts[item.countKey] : undefined;

                return (
                  <Link key={item.href} href={item.href}
                    className={clsx(
                      'flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition mb-0.5',
                      active ? 'bg-blue-500/15 text-blue-400' : 'text-slate-400 hover:text-slate-200 hover:bg-astra-surface-alt'
                    )}
                    title={collapsed ? item.label : undefined}
                  >
                    <item.icon className="h-4 w-4 flex-shrink-0" />
                    {!collapsed && (
                      <>
                        <span className="flex-1">{item.label}</span>
                        {count !== undefined && count > 0 && (
                          <span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] font-bold text-slate-500">
                            {count}
                          </span>
                        )}
                      </>
                    )}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* User footer */}
      {user && (
        <div className="border-t border-astra-border px-3 py-3">
          {!collapsed ? (
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-200 truncate">{user.full_name}</div>
                <div className="text-[10px] text-slate-500 capitalize">{user.role.replace(/_/g, ' ')}</div>
              </div>
              <button onClick={handleLogout}
                className="rounded-lg p-1.5 text-slate-500 hover:text-red-400 transition"
                title="Sign out">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button onClick={handleLogout}
              className="flex w-full items-center justify-center rounded-lg p-2 text-slate-500 hover:text-red-400 transition"
              title="Sign out">
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
      )}
    </aside>
  );
}
