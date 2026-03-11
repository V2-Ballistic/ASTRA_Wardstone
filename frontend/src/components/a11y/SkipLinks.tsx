'use client';

/**
 * ASTRA — Skip Navigation Links
 * ===============================
 * File: frontend/src/components/a11y/SkipLinks.tsx   ← NEW
 *
 * WCAG 2.4.1 (Bypass Blocks): Provides keyboard users a way to
 * skip repetitive navigation and jump directly to main content.
 * Links are visually hidden until focused.
 */

const LINKS = [
  { href: '#main-content', label: 'Skip to main content' },
  { href: '#main-navigation', label: 'Skip to navigation' },
];

export default function SkipLinks() {
  return (
    <div className="skip-links">
      {LINKS.map((link) => (
        <a
          key={link.href}
          href={link.href}
          className="
            fixed left-2 top-2 z-[9999] -translate-y-full
            rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white
            shadow-lg transition-transform duration-200
            focus:translate-y-0
          "
        >
          {link.label}
        </a>
      ))}
    </div>
  );
}
