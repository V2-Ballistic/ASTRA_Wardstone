'use client';

/**
 * ASTRA — Quality tier + motor class badges (Engineering UI)
 * ============================================================
 * File: frontend/src/components/engineering/QualityTierBadge.tsx
 *
 * Tier pill colors per spec §5 UX: excellent=emerald, good=blue,
 * workable=amber. Unknown tiers render slate.
 */

import { ROLE_COLORS, TIER_COLORS } from '@/lib/engineering-types';

export function QualityTierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return <span className="text-slate-600">—</span>;
  const c = TIER_COLORS[tier];
  if (!c) {
    return (
      <span className="rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-semibold text-slate-400">
        {tier}
      </span>
    );
  }
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: c.bg, color: c.text }}
    >
      {c.label}
    </span>
  );
}

/** NAR/TRA total-impulse class letter (H, J, M, …, P+). */
export function MotorClassBadge({ letter }: { letter?: string | null }) {
  if (!letter) return <span className="text-slate-600">—</span>;
  return (
    <span
      className="rounded-md bg-violet-500/15 px-1.5 py-0.5 font-mono text-[11px] font-bold text-violet-300"
      title={`Motor class ${letter}`}
    >
      {letter}
    </span>
  );
}

/** Config BOM role pill (§8 closed taxonomy). Unknown roles render
 *  with the 'other' palette so nothing crashes on future values. */
export function ConfigRoleBadge({ role }: { role?: string | null }) {
  if (!role) return <span className="text-slate-600">—</span>;
  const c = ROLE_COLORS[role] ?? ROLE_COLORS.other;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ background: c.bg, color: c.text }}
    >
      {role}
    </span>
  );
}

/** Revision origin badge: design (solver) vs csv (test/import data). */
export function OriginBadge({ origin }: { origin?: string | null }) {
  if (!origin) return <span className="text-slate-600">—</span>;
  const isDesign = origin === 'design';
  return (
    <span
      className={
        isDesign
          ? 'rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold text-sky-400'
          : 'rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-semibold text-orange-400'
      }
    >
      {isDesign ? 'Design' : origin === 'csv' ? 'CSV' : origin}
    </span>
  );
}
