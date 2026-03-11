/**
 * ASTRA — useAnnounce Hook
 * =========================
 * File: frontend/src/hooks/useAnnounce.ts   ← NEW
 *
 * Wraps the LiveRegionContext for one-liner usage:
 *
 *   const announce = useAnnounce();
 *   announce('3 requirements loaded');
 *   announce('Error: invalid input', 'assertive');
 */

'use client';

import { useLiveRegion } from '@/components/a11y/LiveRegion';

export function useAnnounce() {
  const { announce } = useLiveRegion();
  return announce;
}
