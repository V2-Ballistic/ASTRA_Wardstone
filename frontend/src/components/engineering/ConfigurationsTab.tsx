'use client';

/**
 * ASTRA — Engineering » Configurations tab (PLACEHOLDER)
 * ========================================================
 * File: frontend/src/components/engineering/ConfigurationsTab.tsx
 *
 * Placeholder panel only. The Configurations build
 * (ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §7+) replaces this component and
 * adds its pages under src/app/engineering/configurations/ — keep
 * this file's default export name (`ConfigurationsTab`) stable so the
 * swap is a one-file change.
 */

import Link from 'next/link';
import { Boxes } from 'lucide-react';

export default function ConfigurationsTab() {
  return (
    <div className="rounded-xl border border-dashed border-astra-border-light bg-astra-surface px-6 py-16 text-center">
      <Boxes className="mx-auto mb-3 h-10 w-10 text-slate-600" aria-hidden="true" />
      <h2 className="text-sm font-semibold text-slate-200">
        Configurations coming online
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-xs leading-relaxed text-slate-500">
        Vehicle configurations will assemble a motor revision, an aero deck
        revision, and mass properties into a flight-ready, content-addressed
        bundle. This workspace is being built — in the meantime, prepare its
        inputs in the{' '}
        <Link href="/engineering" className="font-semibold text-blue-400 underline-offset-2 hover:underline">
          Motors
        </Link>{' '}
        and{' '}
        <Link href="/engineering?tab=aero" className="font-semibold text-blue-400 underline-offset-2 hover:underline">
          Aero
        </Link>{' '}
        tabs.
      </p>
    </div>
  );
}
