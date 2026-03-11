/**
 * ASTRA — Jest Test Setup
 * ========================
 * File: frontend/__tests__/setup.ts
 *
 * Mock browser APIs that Next.js / axios depend on.
 */

/* ---------- localStorage mock ---------- */
const store: Record<string, string> = {};

const localStorageMock: Storage = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => {
    store[key] = value;
  },
  removeItem: (key: string) => {
    delete store[key];
  },
  clear: () => {
    Object.keys(store).forEach((k) => delete store[k]);
  },
  get length() {
    return Object.keys(store).length;
  },
  key: (index: number) => Object.keys(store)[index] ?? null,
};

Object.defineProperty(window, "localStorage", { value: localStorageMock });

/* ---------- window.location mock ---------- */
Object.defineProperty(window, "location", {
  value: { href: "", assign: jest.fn(), replace: jest.fn() },
  writable: true,
});

/* ---------- Reset between tests ---------- */
beforeEach(() => {
  localStorageMock.clear();
  jest.clearAllMocks();
});
