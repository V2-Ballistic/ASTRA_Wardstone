'use client';

/**
 * ASTRA — Frontend Auth & RBAC Utilities
 * =======================================
 * Mirrors the backend permission matrix so the UI can
 * show/hide controls without extra API calls.
 *
 * F-024: this file used to live as `auth.ts` alongside a stub
 * `auth.tsx`. Resolution between the two was undefined — we'd been
 * relying on TS module resolution to pick whichever happened to win
 * per build. The stub has been deleted and this file renamed to
 * `auth.tsx` (it contains JSX in `PermissionGate`, so .tsx is
 * correct anyway). The 'use client' directive is required because
 * AuthProvider uses React hooks and `localStorage`.
 */

// ── Role enum (mirrors backend UserRole) ──

export type UserRole =
  | 'admin'
  | 'project_manager'
  | 'requirements_engineer'
  | 'reviewer'
  | 'stakeholder'
  | 'developer';

// ── Permission Matrix (must stay in sync with backend/app/services/rbac.py) ──

const PERMISSION_MATRIX: Record<UserRole, Set<string>> = {
  admin: new Set([
    'requirements.create',
    'requirements.update',
    'requirements.delete',
    'requirements.approve',
    'requirements.baseline',
    'baselines.create',
    'baselines.delete',
    'traceability.create',
    'traceability.delete',
    'projects.create',
    'projects.update',
    'users.manage',
    'settings.manage',
    'reports.export',
    'imports.execute',
  ]),
  project_manager: new Set([
    'requirements.create',
    'requirements.update',
    'requirements.delete',
    'requirements.approve',
    'requirements.baseline',
    'baselines.create',
    'baselines.delete',
    'traceability.create',
    'traceability.delete',
    'projects.create',
    'projects.update',
    'reports.export',
    'imports.execute',
  ]),
  requirements_engineer: new Set([
    'requirements.create',
    'requirements.update',
    'traceability.create',
    'traceability.delete',
    'reports.export',
  ]),
  reviewer: new Set([
    'requirements.approve',
  ]),
  stakeholder: new Set([
    // Read-only + comments. No explicit write permissions.
  ]),
  developer: new Set([
    // Read-only requirements; can update verification status.
  ]),
};

// ── Pure utility ──

/**
 * Check whether a given role has permission for an action.
 *
 * @example
 *   hasPermission('requirements.delete', 'reviewer') // false
 *   hasPermission('requirements.create', 'admin')    // true
 */
export function hasPermission(action: string, role?: string | null): boolean {
  if (!role) return false;
  const perms = PERMISSION_MATRIX[role as UserRole];
  if (!perms) return false;
  return perms.has(action);
}

/**
 * Returns a list of all roles that are allowed the given action.
 */
export function rolesWithPermission(action: string): UserRole[] {
  return (Object.entries(PERMISSION_MATRIX) as [UserRole, Set<string>][])
    .filter(([, perms]) => perms.has(action))
    .map(([role]) => role);
}

/**
 * Returns all permissions for a given role.
 */
export function permissionsForRole(role: string): string[] {
  const perms = PERMISSION_MATRIX[role as UserRole];
  return perms ? Array.from(perms) : [];
}

// ── React hook ──

import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { authAPI } from './api';

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  department?: string;
  is_active: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refresh: async () => {},
});

/**
 * Wrap your app in <AuthProvider> to make user/role info
 * available everywhere via useAuth().
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('astra_token') : null;
      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }
      const res = await authAPI.me();
      setUser(res.data as AuthUser);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (username: string, password: string) => {
    const res = await authAPI.login(username, password);
    // F-025: SSR guard — Next.js renders this provider on the server
    // first, where `localStorage` is undefined. Guarding the writes
    // (already done for the read in refresh()) keeps a server-side
    // re-render from blowing up.
    if (typeof window !== 'undefined') {
      localStorage.setItem('astra_token', res.data.access_token);
    }
    await refresh();
  };

  const logout = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('astra_token');
      // F-027 alignment: drop the project_id stash too. Previously
      // only auth.tsx (the stub) cleared this; the richer auth.ts
      // didn't.
      localStorage.removeItem('astra_project_id');
    }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Access the current authenticated user and auth methods.
 *
 * @example
 *   const { user, logout } = useAuth();
 */
export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Hook: check a single permission against the current user's role.
 *
 * @example
 *   const canDelete = usePermission('requirements.delete');
 *   if (!canDelete) return null; // hide delete button
 */
export function usePermission(action: string): boolean {
  const { user } = useAuth();
  return hasPermission(action, user?.role);
}

/**
 * Hook: check whether the current user has any of the given roles.
 *
 * @example
 *   const isAdminOrPM = useHasRole('admin', 'project_manager');
 */
export function useHasRole(...roles: UserRole[]): boolean {
  const { user } = useAuth();
  if (!user) return false;
  return roles.includes(user.role);
}

// ── Guard component ──

/**
 * Conditionally renders children only if the user has the specified permission.
 *
 * @example
 *   <PermissionGate action="requirements.delete">
 *     <button>Delete</button>
 *   </PermissionGate>
 */
export function PermissionGate({
  action,
  children,
  fallback = null,
}: {
  action: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const allowed = usePermission(action);
  return <>{allowed ? children : fallback}</>;
}
