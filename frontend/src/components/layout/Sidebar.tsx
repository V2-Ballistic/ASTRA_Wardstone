'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  FileText, MonitorDot, MessageSquare, Network, Archive,
  Settings, LayoutDashboard, ChevronRight, LogOut
} from 'lucide-react';
import clsx from 'clsx';
import { useAuth } from '@/lib/auth';
import { requirementsAPI, projectsAPI } from '@/lib/api';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/requirements', label: 'Requirements', icon: FileText, countKey: 'requirements' },
  { href: '/baselines', label: 'Baselines', icon: Archive },
  { href: '/traceability', label: 'Traceability', icon: Network },
  { href: '/interfaces', label: 'Interfaces', icon: MonitorDot },
  { href: '/communication', label: 'Communication', icon: MessageSquare },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [reqCount, setReqCount] = useState<number | null>(null);

  const initials = user?.full_name
    ? user.full_name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : '??';

  // Fetch requirements count
  useEffect(() => {
    if (!user) return;
    projectsAPI.list().then((res) => {
      if (res.data.length > 0) {
        requirementsAPI.list(res.data[0].id, { limit: 1 }).then((rRes) => {
          // The list endpoint returns all matching, so count the full response
          // We'll fetch with high limit to get actual count
          requirementsAPI.list(res.data[0].id, { limit: 200 }).then((fullRes) => {
            setReqCount(fullRes.data.length);
          });
        });
      }
    }).catch(() => {});
  }, [user, pathname]); // Refetch when navigating (catches creates/deletes)

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-astra-border bg-astra-surface">
      {/* Logo */}
      <div className="border-b border-astra-border px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 text-sm font-extrabold text-white">
            A
          </div>
          <div>
            <div className="text-[15px] font-bold tracking-tight text-slate-100">ASTRA</div>
            <div className="text-[10px] font-medium tracking-widest text-slate-500">SYSTEMS ENGINEERING</div>
          </div>
        </div>
      </div>

      {/* Project Selector */}
      <div className="border-b border-astra-border p-3">
        <button className="flex w-full items-center justify-between rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2 transition hover:border-blue-500/30">
          <div>
            <div className="text-xs font-semibold text-slate-200">SMDS</div>
            <div className="text-[10px] text-slate-500">Satellite Missile Deployment</div>
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-slate-500" />
        </button>
      </div>

      {/* Nav Links */}
      <nav className="flex-1 space-y-0.5 p-2">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href ||
            (item.href !== '/' && pathname.startsWith(item.href));
          const Icon = item.icon;
          const count = item.countKey === 'requirements' ? reqCount : undefined;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[13px] font-medium transition-all',
                active
                  ? 'border border-blue-500/20 bg-blue-500/10 text-blue-400'
                  : 'border border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              )}
            >
              <Icon className="h-[18px] w-[18px]" />
              <span className="flex-1">{item.label}</span>
              {count !== undefined && count !== null && (
                <span className={clsx(
                  'rounded-full px-2 py-0.5 text-[10px] font-bold',
                  active ? 'bg-blue-500 text-white' : 'bg-astra-surface-alt text-slate-500'
                )}>
                  {count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="border-t border-astra-border p-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 text-xs font-bold text-white">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-slate-200 truncate">{user?.full_name || 'User'}</div>
            <div className="text-[10px] text-slate-500 truncate">{user?.role?.replace('_', ' ') || ''}</div>
          </div>
          <button onClick={logout} className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition" title="Sign out">
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
