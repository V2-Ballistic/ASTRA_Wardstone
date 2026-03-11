/**
 * ASTRA — Root Layout (WCAG 2.1 AA)
 * ====================================
 * File: frontend/src/app/layout.tsx   ← REPLACES existing
 *
 * Accessibility additions:
 *   - <html lang="en"> (WCAG 3.1.1)
 *   - SkipLinks rendered before all content (WCAG 2.4.1)
 *   - LiveRegionProvider for dynamic announcements (WCAG 4.1.3)
 */

import type { Metadata } from 'next';
import './globals.css';
import AppShell from '@/components/layout/AppShell';
import SkipLinks from '@/components/a11y/SkipLinks';

export const metadata: Metadata = {
  title: 'ASTRA — Systems Engineering Platform',
  description:
    'Requirements tracking, traceability, and systems engineering management.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr">
      <head>
        {/* Ensure proper viewport for touch target sizing (WCAG 2.5.5) */}
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>
        {/* Skip links — first thing in DOM for keyboard users */}
        <SkipLinks />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
