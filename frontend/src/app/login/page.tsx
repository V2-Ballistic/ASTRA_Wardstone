'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { Loader2, Shield, KeyRound, Globe, CreditCard } from 'lucide-react';
import api from '@/lib/api';
import { formatApiError } from '@/lib/errors';

type AuthStep = 'provider' | 'local' | 'mfa';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// F-027 helper: SSR-safe token persistence shared by all non-username
// /password paths (SSO callback, MFA verify, PIV). The username/
// password path goes through useAuth().login() instead.
function _persistTokens(access: string, refresh?: string) {
  if (typeof window === 'undefined') return;
  localStorage.setItem('astra_token', access);
  if (refresh) localStorage.setItem('astra_refresh', refresh);
}

export default function LoginPage() {
  const { login, refresh } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  // F-101: honour ?next= on success — push the requested path
  // instead of always landing on '/'.
  const nextParam = searchParams.get('next') || '/';

  // F-027: SSO callback. Pre-fix this set localStorage and then did
  // `window.location.href = '/'` — which (a) full-page-reloaded,
  // discarding any in-flight state, and (b) the URL still showed
  // `?token=...` in the browser history. Now we use
  // `router.replace(nextParam)` so the URL is rewritten without a
  // history entry, scrubbing the token from the address bar.
  useEffect(() => {
    const token = searchParams.get('token');
    const refreshTok = searchParams.get('refresh');
    if (token) {
      _persistTokens(token, refreshTok || undefined);
      // Refresh the auth context so AuthGate sees the new user.
      refresh().finally(() => {
        router.replace(nextParam);
      });
    }
  }, [searchParams, router, refresh, nextParam]);

  const [step, setStep] = useState<AuthStep>('local');
  const [providers, setProviders] = useState<string[]>(['local']);
  const [mfaRequired, setMfaRequired] = useState(false);

  // Fetch available providers
  useEffect(() => {
    api.get('/auth/providers')
      .then(res => {
        setProviders(res.data.providers || ['local']);
        setMfaRequired(res.data.mfa_required || false);
        if (res.data.providers?.length > 1) {
          setStep('provider');
        }
      })
      .catch(() => {});
  }, []);

  // ── Local login state ──
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mfaToken, setMfaToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [partialToken, setPartialToken] = useState('');

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      // F-027: peek at /auth/login first to detect mfa_required,
      // because useAuth().login() doesn't expose that branch. If the
      // response is a clean token, hand off to the auth context's
      // login() so its refresh() runs and the AuthGate flips
      // immediately. If MFA is required, capture the partial token
      // and switch UI to the MFA step.
      const res = await api.post('/auth/login',
        new URLSearchParams({ username, password }),
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      );
      if (res.data.mfa_required) {
        setPartialToken(res.data.access_token);
        setStep('mfa');
      } else {
        // Use the auth context so the user state updates synchronously.
        await login(username, password);
        router.push(nextParam);
      }
    } catch (err: any) {
      setError(formatApiError(err, 'Invalid credentials'));
    } finally {
      setLoading(false);
    }
  };

  const handleMFA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/mfa/verify',
        { token: mfaToken },
        { headers: { Authorization: `Bearer ${partialToken}` } }
      );
      if (res.data.access_token) {
        _persistTokens(res.data.access_token, res.data.refresh_token);
        await refresh();  // tell the auth context
        router.push(nextParam);
      }
    } catch (err: any) {
      setError(formatApiError(err, 'Invalid MFA token'));
    } finally {
      setLoading(false);
    }
  };

  const handleSSO = (type: 'saml' | 'oidc') => {
    // External redirect — leaves the SPA. window.location is the
    // correct shape here (router.push won't trigger a full-page
    // navigation to a non-Next.js URL).
    window.location.href = `${API_BASE}/auth/${type}/login`;
  };

  const handlePIV = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/auth/piv/authenticate');
      _persistTokens(res.data.access_token, res.data.refresh_token);
      await refresh();
      router.push(nextParam);
    } catch (err: any) {
      setError(formatApiError(err, 'CAC/PIV authentication failed. Ensure your smart card is inserted.'));
    } finally {
      setLoading(false);
    }
  };

  // ── Shared components ──
  const Logo = () => (
    <div className="mb-8 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-500 text-xl font-extrabold text-white shadow-lg shadow-blue-500/25">
        A
      </div>
      <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-100">ASTRA</h1>
      <p className="mt-1 text-xs font-medium tracking-widest text-slate-500">
        SYSTEMS ENGINEERING PLATFORM
      </p>
    </div>
  );

  const ErrorBox = () =>
    error ? (
      <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
        {error}
      </div>
    ) : null;

  const inputClass =
    'w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/25';

  const btnPrimary =
    'flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50';

  const btnSecondary =
    'flex w-full items-center justify-center gap-2.5 rounded-lg border border-astra-border bg-astra-surface-alt py-2.5 text-sm font-medium text-slate-300 transition hover:border-blue-500/30 hover:bg-astra-surface-hover';

  // ── Provider selection ──
  if (step === 'provider') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-astra-bg">
        <div className="w-full max-w-sm">
          <Logo />
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6 space-y-3">
            <p className="text-center text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
              Choose sign-in method
            </p>

            <button onClick={() => setStep('local')} className={btnSecondary}>
              <KeyRound className="h-4 w-4 text-blue-400" /> Username &amp; Password
            </button>

            {providers.includes('saml') && (
              <button onClick={() => handleSSO('saml')} className={btnSecondary}>
                <Globe className="h-4 w-4 text-emerald-400" /> Sign in with SSO (SAML)
              </button>
            )}

            {providers.includes('oidc') && (
              <button onClick={() => handleSSO('oidc')} className={btnSecondary}>
                <Globe className="h-4 w-4 text-violet-400" /> Sign in with SSO (OIDC)
              </button>
            )}

            {providers.includes('piv') && (
              <button onClick={handlePIV} disabled={loading} className={btnSecondary}>
                <CreditCard className="h-4 w-4 text-amber-400" />
                {loading ? 'Authenticating…' : 'Login with CAC / PIV'}
              </button>
            )}

            <ErrorBox />
          </div>
          <p className="mt-4 text-center text-[11px] text-slate-600">
            ASTRA v1.0 · Internal Use Only
          </p>
        </div>
      </div>
    );
  }

  // ── MFA step ──
  if (step === 'mfa') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-astra-bg">
        <div className="w-full max-w-sm">
          <Logo />
          <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
            <div className="mb-4 flex items-center justify-center gap-2 text-emerald-400">
              <Shield className="h-5 w-5" />
              <span className="text-sm font-semibold">Multi-Factor Authentication</span>
            </div>
            <p className="mb-4 text-center text-xs text-slate-500">
              Enter the 6-digit code from your authenticator app
            </p>
            <form onSubmit={handleMFA} className="space-y-4">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={mfaToken}
                onChange={e => setMfaToken(e.target.value.replace(/\D/g, ''))}
                className={inputClass + ' text-center text-lg tracking-[0.5em] font-mono'}
                placeholder="000000"
                autoFocus
                required
              />
              <ErrorBox />
              <button type="submit" disabled={loading || mfaToken.length < 6} className={btnPrimary}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Verify
              </button>
            </form>
            <button
              onClick={() => { setStep('local'); setError(''); setMfaToken(''); }}
              className="mt-3 w-full text-center text-xs text-slate-500 hover:text-slate-300"
            >
              ← Back to login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Local username/password ──
  return (
    <div className="flex min-h-screen items-center justify-center bg-astra-bg">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <form onSubmit={handleLocalLogin} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className={inputClass}
                placeholder="Enter username"
                required
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className={inputClass}
                placeholder="Enter password"
                required
              />
            </div>
            <ErrorBox />
            <button type="submit" disabled={loading} className={btnPrimary}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          {providers.length > 1 && (
            <>
              <div className="my-4 flex items-center gap-3">
                <div className="h-px flex-1 bg-astra-border" />
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">or</span>
                <div className="h-px flex-1 bg-astra-border" />
              </div>
              <button
                onClick={() => { setStep('provider'); setError(''); }}
                className={btnSecondary}
              >
                Other sign-in methods
              </button>
            </>
          )}
        </div>
        <p className="mt-4 text-center text-[11px] text-slate-600">
          ASTRA v1.0 · Internal Use Only
        </p>
      </div>
    </div>
  );
}
