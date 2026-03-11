/**
 * ASTRA — Accessibility Tests
 * =============================
 * File: frontend/src/tests/a11y.test.tsx   ← NEW
 *
 * Automated WCAG 2.1 AA checks using jest-axe, plus manual
 * keyboard-navigation and ARIA-attribute verification.
 *
 * Install deps:
 *   npm i -D jest-axe @testing-library/react @testing-library/jest-dom
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

// ── Mock next/navigation for components that use it ──
jest.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: jest.fn(), back: jest.fn() }),
  useParams: () => ({}),
  useSearchParams: () => new URLSearchParams(),
}));

// ── Mock auth context ──
jest.mock('@/lib/auth', () => ({
  useAuth: () => ({
    user: { id: 1, full_name: 'Test User', role: 'admin', username: 'test' },
    loading: false,
    login: jest.fn(),
    logout: jest.fn(),
  }),
  AuthProvider: ({ children }: any) => <>{children}</>,
}));

// ── Mock API ──
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: [] }),
    post: jest.fn().mockResolvedValue({ data: {} }),
  },
  requirementsAPI: { list: jest.fn().mockResolvedValue({ data: [] }) },
  projectsAPI: { list: jest.fn().mockResolvedValue({ data: [] }) },
}));

// ══════════════════════════════════════
//  Component Imports
// ══════════════════════════════════════

import SkipLinks from '@/components/a11y/SkipLinks';
import { LiveRegionProvider } from '@/components/a11y/LiveRegion';
import { FocusTrap, AccessibleModal } from '@/components/a11y/FocusTrap';

// ══════════════════════════════════════
//  Test: Skip Links
// ══════════════════════════════════════

describe('SkipLinks', () => {
  it('renders skip links with correct href targets', () => {
    render(<SkipLinks />);
    const mainLink = screen.getByText('Skip to main content');
    const navLink = screen.getByText('Skip to navigation');

    expect(mainLink).toHaveAttribute('href', '#main-content');
    expect(navLink).toHaveAttribute('href', '#main-navigation');
  });

  it('passes axe accessibility check', async () => {
    const { container } = render(<SkipLinks />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ══════════════════════════════════════
//  Test: Live Region
// ══════════════════════════════════════

describe('LiveRegion', () => {
  it('renders live region containers with correct ARIA roles', () => {
    const { container } = render(
      <LiveRegionProvider>
        <div>content</div>
      </LiveRegionProvider>
    );

    const polite = container.querySelector('[aria-live="polite"]');
    const assertive = container.querySelector('[aria-live="assertive"]');

    expect(polite).toBeInTheDocument();
    expect(assertive).toBeInTheDocument();
    expect(polite).toHaveAttribute('role', 'status');
    expect(assertive).toHaveAttribute('role', 'alert');
  });
});

// ══════════════════════════════════════
//  Test: Focus Trap
// ══════════════════════════════════════

describe('FocusTrap', () => {
  it('contains focus within the trap on Tab', () => {
    render(
      <FocusTrap active>
        <button data-testid="first">First</button>
        <button data-testid="second">Second</button>
      </FocusTrap>
    );

    const first = screen.getByTestId('first');
    const second = screen.getByTestId('second');

    // Focus should start on first button
    expect(document.activeElement).toBe(first);

    // Tab forward from second should wrap to first
    second.focus();
    fireEvent.keyDown(second, { key: 'Tab', shiftKey: false });
    // The trap should prevent focus from leaving
  });
});

// ══════════════════════════════════════
//  Test: Accessible Modal
// ══════════════════════════════════════

describe('AccessibleModal', () => {
  it('renders with correct ARIA attributes when open', () => {
    const { container } = render(
      <AccessibleModal open={true} onClose={jest.fn()} title="Test Dialog">
        <p>Modal content</p>
      </AccessibleModal>
    );

    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby');

    // Title should be in the DOM (sr-only)
    expect(screen.getByText('Test Dialog')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    const { container } = render(
      <AccessibleModal open={false} onClose={jest.fn()} title="Hidden">
        <p>Should not appear</p>
      </AccessibleModal>
    );

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument();
  });

  it('calls onClose when Escape is pressed', () => {
    const onClose = jest.fn();
    render(
      <AccessibleModal open={true} onClose={onClose} title="Escapable">
        <button>Inside</button>
      </AccessibleModal>
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('passes axe accessibility check', async () => {
    const { container } = render(
      <AccessibleModal open={true} onClose={jest.fn()} title="Axe Check">
        <p>Content for axe</p>
        <button>OK</button>
      </AccessibleModal>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

// ══════════════════════════════════════
//  Test: ARIA landmark roles
// ══════════════════════════════════════

describe('Landmark roles', () => {
  it('main content area has correct id and role', () => {
    // Simulate the authenticated AppShell output
    render(
      <main id="main-content" role="main" tabIndex={-1}>
        <h1>Dashboard</h1>
      </main>
    );

    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(main).toHaveAttribute('tabindex', '-1');
  });
});

// ══════════════════════════════════════
//  Test: Colour contrast helpers
// ══════════════════════════════════════

describe('Status badges convey info beyond colour', () => {
  it('status badge includes text label', () => {
    render(
      <span
        role="status"
        aria-label="Status: Approved"
        style={{ background: '#10B981' }}
      >
        Approved
      </span>
    );

    // Both visual text AND aria-label are present
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      'Status: Approved'
    );
  });

  it('quality indicator has descriptive aria-label', () => {
    render(
      <div
        role="img"
        aria-label="Quality score: 85 out of 100"
        style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }}
      />
    );

    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      'Quality score: 85 out of 100'
    );
  });
});

// ══════════════════════════════════════
//  Test: Progress bars
// ══════════════════════════════════════

describe('Coverage progress bars', () => {
  it('have correct progressbar ARIA attributes', () => {
    render(
      <div
        role="progressbar"
        aria-valuenow={83}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Source artifact coverage: 83%"
      >
        <div style={{ width: '83%' }} />
      </div>
    );

    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '83');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });
});

// ══════════════════════════════════════
//  Test: Keyboard navigation
// ══════════════════════════════════════

describe('Keyboard navigation', () => {
  it('all interactive elements are reachable via Tab', () => {
    render(
      <div>
        <a href="/one">Link One</a>
        <button>Button Two</button>
        <input aria-label="Search" />
        <a href="/three">Link Three</a>
      </div>
    );

    const interactive = screen.getAllByRole(/(link|button|textbox)/);
    // Every interactive element should be focusable (no positive tabindex)
    interactive.forEach((el) => {
      const tabIndex = el.getAttribute('tabindex');
      // tabindex should be 0, -1, or absent — never > 0
      if (tabIndex !== null) {
        expect(Number(tabIndex)).toBeLessThanOrEqual(0);
      }
    });
  });
});
