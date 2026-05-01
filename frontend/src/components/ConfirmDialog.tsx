'use client';

/**
 * ASTRA — Confirmation modal (F-091)
 * ====================================
 * File: frontend/src/components/ConfirmDialog.tsx
 *
 * Drop-in replacement for `window.confirm()` that:
 *   - matches the existing astra-surface modal styling so it doesn't
 *     look like a system browser dialog,
 *   - is keyboard-accessible (Escape cancels, Enter confirms when
 *     the confirm button is focused),
 *   - exposes role="dialog" and an aria-labelled heading for
 *     screen readers,
 *   - supports a `destructive` flag that swaps the confirm button to
 *     red and labels the action.
 *
 * Usage:
 *
 *     const [open, setOpen] = useState(false);
 *     <ConfirmDialog
 *       open={open}
 *       title="Delete this baseline?"
 *       message="Snapshots will be archived but the baseline will no longer be selectable."
 *       confirmLabel="Delete"
 *       destructive
 *       onCancel={() => setOpen(false)}
 *       onConfirm={() => { setOpen(false); doDelete(); }}
 *     />
 */

import { useEffect, useRef } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  // Auto-focus the confirm button when the dialog opens, and bind
  // Escape → cancel.
  useEffect(() => {
    if (!open) return;
    confirmBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCancel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const confirmClass = destructive
    ? 'bg-red-500 hover:bg-red-600 focus:ring-red-500/40'
    : 'bg-blue-500 hover:bg-blue-600 focus:ring-blue-500/40';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3
          id="confirm-dialog-title"
          className="text-sm font-bold text-slate-100"
        >
          {title}
        </h3>
        {message && (
          <p className="mt-2 text-xs text-slate-400">{message}</p>
        )}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            ref={confirmBtnRef}
            onClick={onConfirm}
            className={`rounded-lg px-4 py-2 text-xs font-semibold text-white outline-none focus:ring-2 ${confirmClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
