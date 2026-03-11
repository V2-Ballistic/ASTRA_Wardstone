'use client';

/**
 * ASTRA — Focus Trap & Accessible Modal
 * =======================================
 * File: frontend/src/components/a11y/FocusTrap.tsx   ← NEW
 *
 * WCAG 2.4.3 (Focus Order) + 2.1.2 (No Keyboard Trap):
 * - FocusTrap: constrains Tab focus within a container
 * - AccessibleModal: full dialog pattern with role="dialog",
 *   aria-modal, focus trap, Escape-to-close, and focus restoration.
 */

import {
  useRef, useEffect, useCallback, type ReactNode, type KeyboardEvent,
} from 'react';

// ══════════════════════════════════════
//  Focus Trap
// ══════════════════════════════════════

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), ' +
  'input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface FocusTrapProps {
  children: ReactNode;
  active?: boolean;
  className?: string;
}

export function FocusTrap({ children, active = true, className }: FocusTrapProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Trap Tab key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (!active || e.key !== 'Tab') return;
      const container = ref.current;
      if (!container) return;

      const focusable = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE)
      ).filter((el) => el.offsetParent !== null); // visible only

      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [active]
  );

  // Auto-focus first focusable element
  useEffect(() => {
    if (!active || !ref.current) return;
    const first = ref.current.querySelector<HTMLElement>(FOCUSABLE);
    if (first) {
      // Small delay so the DOM is painted first
      requestAnimationFrame(() => first.focus());
    }
  }, [active]);

  return (
    <div ref={ref} onKeyDown={handleKeyDown as any} className={className}>
      {children}
    </div>
  );
}

// ══════════════════════════════════════
//  Accessible Modal
// ══════════════════════════════════════

interface AccessibleModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** id of the element that triggered the modal — focus returns here on close */
  triggerId?: string;
  children: ReactNode;
  className?: string;
}

export function AccessibleModal({
  open,
  onClose,
  title,
  triggerId,
  children,
  className = '',
}: AccessibleModalProps) {
  const titleId = useRef(`modal-title-${Math.random().toString(36).slice(2, 8)}`);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Save the trigger element's focus on open
  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
    }
  }, [open]);

  // Restore focus on close
  useEffect(() => {
    if (!open && previousFocusRef.current) {
      const target = triggerId
        ? document.getElementById(triggerId)
        : previousFocusRef.current;
      target?.focus();
    }
  }, [open, triggerId]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Prevent body scroll while modal is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="presentation"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Dialog */}
      <FocusTrap active>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId.current}
          className={`relative z-10 w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl ${className}`}
        >
          <h2 id={titleId.current} className="sr-only">
            {title}
          </h2>
          {children}
        </div>
      </FocusTrap>
    </div>
  );
}
