'use client';

/**
 * ASTRA — ARIA Live Region
 * =========================
 * File: frontend/src/components/a11y/LiveRegion.tsx   ← NEW
 *
 * WCAG 4.1.3 (Status Messages): Provides a visually-hidden live
 * region that screen readers announce when content changes.
 *
 * Usage:
 *   import { announce } from '@/hooks/useAnnounce';
 *   announce('Requirement created successfully');
 */

import { useState, useEffect, useCallback, createContext, useContext } from 'react';

interface LiveRegionContextValue {
  announce: (message: string, priority?: 'polite' | 'assertive') => void;
}

export const LiveRegionContext = createContext<LiveRegionContextValue>({
  announce: () => {},
});

export function LiveRegionProvider({ children }: { children: React.ReactNode }) {
  const [politeMsg, setPoliteMsg] = useState('');
  const [assertiveMsg, setAssertiveMsg] = useState('');

  const announce = useCallback(
    (message: string, priority: 'polite' | 'assertive' = 'polite') => {
      if (priority === 'assertive') {
        setAssertiveMsg('');
        // Force re-render so screen reader re-announces
        requestAnimationFrame(() => setAssertiveMsg(message));
      } else {
        setPoliteMsg('');
        requestAnimationFrame(() => setPoliteMsg(message));
      }
    },
    []
  );

  // Auto-clear after 5 seconds
  useEffect(() => {
    if (!politeMsg) return;
    const t = setTimeout(() => setPoliteMsg(''), 5000);
    return () => clearTimeout(t);
  }, [politeMsg]);

  useEffect(() => {
    if (!assertiveMsg) return;
    const t = setTimeout(() => setAssertiveMsg(''), 5000);
    return () => clearTimeout(t);
  }, [assertiveMsg]);

  return (
    <LiveRegionContext.Provider value={{ announce }}>
      {children}

      {/* Visually hidden live regions */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {politeMsg}
      </div>
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      >
        {assertiveMsg}
      </div>
    </LiveRegionContext.Provider>
  );
}

export function useLiveRegion() {
  return useContext(LiveRegionContext);
}
