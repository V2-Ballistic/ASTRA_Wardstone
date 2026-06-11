'use client';

/**
 * ASTRA — Drag-drop upload zone (Engineering UI headline UX)
 * ============================================================
 * File: frontend/src/components/engineering/UploadDropzone.tsx
 *
 * Dashed-border dropzone with a hidden file-input fallback (click or
 * Enter/Space to browse). The parent owns the actual POST + role
 * gating — this component only collects File objects.
 */

import { useCallback, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { Loader2, UploadCloud } from 'lucide-react';
import clsx from 'clsx';

export interface UploadDropzoneProps {
  /** Headline, e.g. "Drop a motor CSV here". */
  label: string;
  /** Secondary line, e.g. "HAROLD names it — you don't." */
  sublabel?: string;
  /** input accept attribute, e.g. ".csv,text/csv". */
  accept?: string;
  multiple?: boolean;
  uploading?: boolean;
  uploadingLabel?: string;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
  className?: string;
  /** Compact variant for detail-page "add revision" zones. */
  compact?: boolean;
}

export default function UploadDropzone({
  label,
  sublabel,
  accept,
  multiple = false,
  uploading = false,
  uploadingLabel = 'Uploading…',
  disabled = false,
  onFiles,
  className,
  compact = false,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const inactive = disabled || uploading;

  const emit = useCallback((list: FileList | null) => {
    if (!list || list.length === 0) return;
    const files = Array.from(list);
    onFiles(multiple ? files : files.slice(0, 1));
  }, [multiple, onFiles]);

  const onDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (inactive) return;
    emit(e.dataTransfer?.files ?? null);
  }, [emit, inactive]);

  const onKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    if (inactive) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      inputRef.current?.click();
    }
  }, [inactive]);

  return (
    <div
      role="button"
      tabIndex={inactive ? -1 : 0}
      aria-disabled={inactive}
      aria-label={label}
      onClick={() => { if (!inactive) inputRef.current?.click(); }}
      onKeyDown={onKeyDown}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!inactive) setDragOver(true);
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        setDragOver(false);
      }}
      onDrop={onDrop}
      className={clsx(
        'flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed text-center transition outline-none',
        compact ? 'px-4 py-4' : 'px-6 py-8',
        dragOver
          ? 'border-emerald-500/60 bg-emerald-500/10'
          : 'border-astra-border-light bg-astra-surface hover:border-emerald-500/40 hover:bg-astra-surface-alt',
        inactive && 'cursor-not-allowed opacity-60',
        'focus-visible:ring-2 focus-visible:ring-blue-500/50',
        className,
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => {
          emit(e.target.files);
          e.target.value = '';
        }}
      />
      {uploading ? (
        <>
          <Loader2 className={clsx('animate-spin text-emerald-400', compact ? 'h-5 w-5' : 'h-7 w-7')} aria-hidden="true" />
          <div className="text-xs font-semibold text-emerald-300">{uploadingLabel}</div>
        </>
      ) : (
        <>
          <UploadCloud className={clsx('text-slate-500', compact ? 'h-5 w-5' : 'h-7 w-7')} aria-hidden="true" />
          <div className={clsx('font-semibold text-slate-200', compact ? 'text-xs' : 'text-sm')}>
            {label}
          </div>
          {sublabel && <div className="text-[11px] text-slate-500">{sublabel}</div>}
          <div className="text-[10px] text-slate-600">
            drag &amp; drop, or click to browse
          </div>
        </>
      )}
    </div>
  );
}
