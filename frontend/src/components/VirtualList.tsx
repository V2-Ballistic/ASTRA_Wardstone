'use client';

/**
 * ASTRA — Lightweight virtualized list (F-098, F-129)
 * =====================================================
 * File: frontend/src/components/VirtualList.tsx
 *
 * Minimal fixed-row-height windowing without an external dep
 * (`react-window` / `@tanstack/react-virtual` would be cleaner but
 * each adds ~30KB to the bundle and a new transitive). Renders only
 * the rows currently in the scroll viewport plus an overscan buffer.
 *
 * Use it when the row count is large enough that the per-row React
 * cost dominates (typically > 100). For smaller lists, render the
 * full array — the constant overhead of the windowed bookkeeping
 * isn't worth it.
 *
 * Constraints:
 *   - Every row must have the same height (passed via `rowHeight`).
 *     Rows with truncate / line-clamp work fine; flowing
 *     variable-height content does not.
 *   - The container's height is fixed via `containerHeight`.
 *   - `renderRow(item, index)` should return a single block-level
 *     element with the same height as `rowHeight`.
 */

import { useState, useEffect, useRef, useMemo, type ReactNode } from 'react';

interface VirtualListProps<T> {
  items: T[];
  rowHeight: number;
  containerHeight: number;
  overscan?: number;
  renderRow: (item: T, index: number) => ReactNode;
  className?: string;
  /** Stable key for each row — defaults to array index, which is
   * fine when the items array is append-only but bad on filter/sort
   * changes. Pass a function returning `item.id` (or similar) for
   * stable rendering across re-orderings. */
  keyOf?: (item: T, index: number) => string | number;
}

export default function VirtualList<T>({
  items,
  rowHeight,
  containerHeight,
  overscan = 5,
  renderRow,
  className,
  keyOf,
}: VirtualListProps<T>) {
  const [scrollTop, setScrollTop] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  // Reset scroll when the items array shrinks past the current top
  // (e.g. filter clears most rows away).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const max = Math.max(0, items.length * rowHeight - containerHeight);
    if (scrollTop > max) {
      el.scrollTop = max;
      setScrollTop(max);
    }
  }, [items.length, rowHeight, containerHeight, scrollTop]);

  const { startIndex, endIndex, padTop, padBottom } = useMemo(() => {
    const total = items.length;
    if (total === 0) {
      return { startIndex: 0, endIndex: 0, padTop: 0, padBottom: 0 };
    }
    const visibleCount = Math.ceil(containerHeight / rowHeight);
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const end = Math.min(total, start + visibleCount + overscan * 2);
    return {
      startIndex: start,
      endIndex: end,
      padTop: start * rowHeight,
      padBottom: Math.max(0, (total - end) * rowHeight),
    };
  }, [items.length, rowHeight, containerHeight, scrollTop, overscan]);

  const slice = items.slice(startIndex, endIndex);

  return (
    <div
      ref={ref}
      className={className}
      style={{ height: containerHeight, overflowY: 'auto' }}
      onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
    >
      {padTop > 0 && <div style={{ height: padTop }} aria-hidden="true" />}
      {slice.map((item, i) => {
        const absoluteIndex = startIndex + i;
        const key = keyOf ? keyOf(item, absoluteIndex) : absoluteIndex;
        return (
          <div key={key} style={{ height: rowHeight }}>
            {renderRow(item, absoluteIndex)}
          </div>
        );
      })}
      {padBottom > 0 && <div style={{ height: padBottom }} aria-hidden="true" />}
    </div>
  );
}
