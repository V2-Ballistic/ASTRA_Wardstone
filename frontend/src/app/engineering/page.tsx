'use client';

/**
 * ASTRA — Engineering Landing Page (spec §4)
 * ============================================
 * File: frontend/src/app/engineering/page.tsx
 *
 * Three tabs: Motors | Aero | Configurations — same tab pattern as
 * /catalog, with the active tab reflected in ?tab= so detail pages
 * can deep-link (e.g. "use in config" → /engineering?tab=configurations).
 *
 * Each tab's content lives in its own component file under
 * src/components/engineering/ so the Configurations build can swap
 * its placeholder without touching this page.
 */

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Boxes, Flame, Rocket, Wind } from 'lucide-react';
import clsx from 'clsx';

import MotorsTab from '@/components/engineering/MotorsTab';
import AeroTab from '@/components/engineering/AeroTab';
import ConfigurationsTab from '@/components/engineering/ConfigurationsTab';

type Tab = 'motors' | 'aero' | 'configurations';

export default function EngineeringLandingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tabParam = searchParams?.get('tab');
  const tab: Tab =
    tabParam === 'aero' || tabParam === 'configurations' ? tabParam : 'motors';

  const setTab = (t: Tab) => {
    router.replace(t === 'motors' ? '/engineering' : `/engineering?tab=${t}`, {
      scroll: false,
    });
  };

  const tabs: { key: Tab; label: string; icon: typeof Flame }[] = useMemo(() => ([
    { key: 'motors',         label: 'Motors',         icon: Flame },
    { key: 'aero',           label: 'Aero',           icon: Wind },
    { key: 'configurations', label: 'Configurations', icon: Boxes },
  ]), []);

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            <Rocket className="h-6 w-6 text-blue-400" aria-hidden="true" />
            Engineering
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            HAROLD-named engineering data products — motors, aero decks, and
            vehicle configurations. Revisions are immutable; new data means a
            new revision.
          </p>
        </div>
      </div>

      <div role="tablist" aria-label="Engineering sections" className="mb-4 flex gap-1 border-b border-astra-border">
        {tabs.map(({ key, label, icon: Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`engineering-panel-${key}`}
              id={`engineering-tab-${key}`}
              onClick={() => setTab(key)}
              className={clsx(
                'flex items-center gap-1.5 rounded-t-lg border-b-2 px-4 py-2 text-xs font-semibold transition',
                active
                  ? 'border-blue-400 text-blue-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200',
              )}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>

      <div id={`engineering-panel-${tab}`} role="tabpanel" aria-labelledby={`engineering-tab-${tab}`}>
        {tab === 'motors' && <MotorsTab />}
        {tab === 'aero' && <AeroTab />}
        {tab === 'configurations' && <ConfigurationsTab />}
      </div>
    </div>
  );
}
