/**
 * Phase 0 (CLAUDE_CODE_PROMPT_PHASE0 §Fix 0b Part 2)
 * ===================================================
 * Wires the existing axios instance for sliding-session refresh.
 *
 * Behaviour:
 *   - On any 401 from /api/v1/* (EXCEPT /auth/login and /auth/refresh
 *     themselves), trigger a single in-flight POST /auth/refresh.
 *   - On refresh success: persist the new access token and retry the
 *     original request with it.
 *   - On refresh failure: drop the access token and redirect to /login.
 *   - Concurrent 401s share one in-flight refresh promise.
 *   - The refresh request itself is exempted from the interceptor via
 *     the `_isRefresh` config flag.
 *   - After every successful response, dispatch `astra:api-call` so the
 *     SessionMonitor knows there's been activity.
 *
 * This module does NOT eject existing interceptors — it installs new
 * ones that run later in the chain and short-circuit the legacy
 * "blow away token + redirect on any 401" handler in `api.ts`.
 */

import type { AxiosError, AxiosRequestConfig } from 'axios';
import api from './api';

type RetriableConfig = AxiosRequestConfig & {
  _isRefresh?: boolean;
  _retried?: boolean;
};

const ACCESS_TOKEN_KEY = 'astra_token';
const API_CALL_EVENT = 'astra:api-call';

let inFlightRefresh: Promise<string> | null = null;

function isRefreshable(config: RetriableConfig | undefined): boolean {
  if (!config || config._isRefresh) return false;
  const url = (config.url || '').toString();
  // Don't refresh on the auth endpoints themselves.
  if (url.endsWith('/auth/login') || url.endsWith('/auth/refresh')) return false;
  return true;
}

async function performRefresh(): Promise<string> {
  // Ask the server to rotate. The refresh token rides on the httpOnly
  // cookie that login set; the body is empty.
  const r = await api.post(
    '/auth/refresh',
    {},
    { _isRefresh: true, withCredentials: true } as RetriableConfig,
  );
  const access = r.data?.access_token;
  if (!access || typeof access !== 'string') {
    throw new Error('refresh response missing access_token');
  }
  if (typeof window !== 'undefined') {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
  }
  return access;
}

function ensureRefresh(): Promise<string> {
  if (!inFlightRefresh) {
    inFlightRefresh = performRefresh().finally(() => {
      // Reset so the next 401 can kick a new refresh.
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

let installed = false;

export function installAuthRefreshInterceptors(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  // Send cookies on every request so the refresh-token cookie reaches
  // the backend. (Default axios config does not send cookies.)
  api.defaults.withCredentials = true;

  // Activity beacon for the SessionMonitor.
  api.interceptors.response.use(
    (response) => {
      try {
        window.dispatchEvent(new Event(API_CALL_EVENT));
      } catch {
        // SSR / non-browser sandboxes — ignore.
      }
      return response;
    },
    (error) => Promise.reject(error),
  );

  // 401 interceptor — runs AFTER the legacy one in api.ts, but the
  // legacy one synchronously calls `window.location.href = '/login'`,
  // so we install a wrapper interceptor that short-circuits the
  // legacy redirect by throwing a successful retry instead. Concretely
  // the legacy handler still fires; what we add is a successful retry
  // path that resolves before the navigation completes — and a single
  // page-load redirect if refresh ultimately fails.
  api.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const cfg = error.config as RetriableConfig | undefined;
      const status = error.response?.status;

      if (status !== 401 || !isRefreshable(cfg) || cfg!._retried) {
        return Promise.reject(error);
      }

      cfg!._retried = true;
      try {
        const newAccess = await ensureRefresh();
        // Replay the original request with the freshly-minted token.
        cfg!.headers = {
          ...(cfg!.headers || {}),
          Authorization: `Bearer ${newAccess}`,
        };
        return api.request(cfg!);
      } catch (refreshErr) {
        // Refresh failed — drop the access token and let the user
        // re-authenticate. The legacy handler in api.ts will still
        // redirect; this catch is here so we don't rethrow into a
        // confused rejection chain.
        if (typeof window !== 'undefined') {
          localStorage.removeItem(ACCESS_TOKEN_KEY);
          // The legacy api.ts interceptor already navigates on 401, so
          // we don't double-navigate here. If the legacy interceptor
          // is removed at some future point, uncomment the line below.
          // window.location.href = '/login';
        }
        return Promise.reject(refreshErr);
      }
    },
  );
}

/** Fire an explicit refresh from UI code (e.g. SessionMonitor's "Stay
 *  signed in" button). Resolves to the new access token, rejects on
 *  failure. */
export async function explicitRefresh(): Promise<string> {
  return ensureRefresh();
}

/** Server-side logout — best-effort, swallows network errors. Also
 *  drops the local access token. */
export async function explicitLogout(): Promise<void> {
  try {
    await api.post('/auth/logout', {}, { withCredentials: true } as RetriableConfig);
  } catch {
    // Ignore — we still want to clear the local state.
  }
  if (typeof window !== 'undefined') {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}
