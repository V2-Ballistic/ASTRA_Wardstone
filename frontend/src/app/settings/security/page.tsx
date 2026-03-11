'use client';

import { useState, useEffect } from 'react';
import {
  Shield, Smartphone, Key, Monitor, Trash2, Loader2,
  CheckCircle, AlertTriangle, Copy, Eye, EyeOff,
} from 'lucide-react';
import api from '@/lib/api';

interface Session {
  id: number;
  provider: string;
  ip_address: string;
  user_agent: string;
  created_at: string;
}

export default function SecuritySettingsPage() {
  // ── MFA state ──
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [mfaSetupData, setMfaSetupData] = useState<{
    provisioning_uri: string;
    qr_data_uri: string;
  } | null>(null);
  const [mfaToken, setMfaToken] = useState('');
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaMsg, setMfaMsg] = useState('');
  const [showSecret, setShowSecret] = useState(false);

  // ── Sessions state ──
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessLoading, setSessLoading] = useState(true);

  // ── Password state ──
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwMsg, setPwMsg] = useState('');

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    setSessLoading(true);
    try {
      const res = await api.get('/auth/sessions');
      setSessions(res.data);
    } catch { /* ignore */ }
    setSessLoading(false);
  };

  // ── MFA Setup ──
  const startMfaSetup = async () => {
    setMfaLoading(true);
    setMfaMsg('');
    try {
      const res = await api.post('/auth/mfa/setup');
      setMfaSetupData(res.data);
    } catch (err: any) {
      setMfaMsg(err.response?.data?.detail || 'Failed to start MFA setup');
    }
    setMfaLoading(false);
  };

  const confirmMfa = async () => {
    setMfaLoading(true);
    setMfaMsg('');
    try {
      await api.post('/auth/mfa/verify', { token: mfaToken });
      setMfaEnabled(true);
      setMfaSetupData(null);
      setMfaMsg('MFA enabled successfully');
      setMfaToken('');
    } catch (err: any) {
      setMfaMsg(err.response?.data?.detail || 'Invalid code');
    }
    setMfaLoading(false);
  };

  const disableMfa = async () => {
    try {
      await api.post('/auth/mfa/disable');
      setMfaEnabled(false);
      setMfaMsg('MFA disabled');
    } catch (err: any) {
      setMfaMsg(err.response?.data?.detail || 'Failed');
    }
  };

  // ── Style helpers ──
  const card = 'rounded-xl border border-astra-border bg-astra-surface p-6';
  const inputClass =
    'w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/25';
  const btnPrimary =
    'flex items-center justify-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50';
  const btnDanger =
    'flex items-center justify-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-400 transition hover:bg-red-500/20';

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-xl font-bold tracking-tight">Security Settings</h1>
      <p className="mb-6 text-sm text-slate-500">
        Manage authentication, MFA, and active sessions
      </p>

      {/* ── MFA Section ── */}
      <div className={card + ' mb-6'}>
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/15">
            <Shield className="h-4 w-4 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100">Multi-Factor Authentication</h2>
            <p className="text-xs text-slate-500">
              {mfaEnabled ? 'MFA is active' : 'Add a second factor for extra security'}
            </p>
          </div>
          {mfaEnabled && (
            <span className="ml-auto rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-bold text-emerald-400">
              ENABLED
            </span>
          )}
        </div>

        {/* Setup flow */}
        {!mfaEnabled && !mfaSetupData && (
          <button onClick={startMfaSetup} disabled={mfaLoading} className={btnPrimary}>
            {mfaLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Smartphone className="h-4 w-4" />}
            Set Up MFA
          </button>
        )}

        {mfaSetupData && (
          <div className="space-y-4">
            <p className="text-xs text-slate-400">
              Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
            </p>

            {mfaSetupData.qr_data_uri ? (
              <div className="flex justify-center">
                <img
                  src={mfaSetupData.qr_data_uri}
                  alt="MFA QR Code"
                  className="h-48 w-48 rounded-lg border border-astra-border bg-white p-2"
                />
              </div>
            ) : (
              <div className="rounded-lg border border-astra-border bg-astra-surface-alt p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    Manual entry URI
                  </span>
                  <button
                    onClick={() => setShowSecret(!showSecret)}
                    className="text-slate-500 hover:text-slate-300"
                  >
                    {showSecret ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                  </button>
                </div>
                <code className="block break-all text-xs text-slate-300">
                  {showSecret ? mfaSetupData.provisioning_uri : '••••••••••••'}
                </code>
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Enter 6-digit code to confirm
              </label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={mfaToken}
                onChange={e => setMfaToken(e.target.value.replace(/\D/g, ''))}
                className={inputClass + ' text-center font-mono text-lg tracking-[0.5em]'}
                placeholder="000000"
              />
            </div>

            <button
              onClick={confirmMfa}
              disabled={mfaLoading || mfaToken.length < 6}
              className={btnPrimary}
            >
              {mfaLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
              Verify &amp; Enable
            </button>
          </div>
        )}

        {mfaEnabled && (
          <button onClick={disableMfa} className={btnDanger}>
            Disable MFA
          </button>
        )}

        {mfaMsg && (
          <p className="mt-3 text-xs text-slate-400">{mfaMsg}</p>
        )}
      </div>

      {/* ── Active Sessions ── */}
      <div className={card + ' mb-6'}>
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/15">
            <Monitor className="h-4 w-4 text-blue-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100">Active Sessions</h2>
            <p className="text-xs text-slate-500">{sessions.length} session(s)</p>
          </div>
        </div>

        {sessLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
          </div>
        ) : sessions.length === 0 ? (
          <p className="text-sm text-slate-500">No active sessions found.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map(s => (
              <div
                key={s.id}
                className="flex items-center gap-3 rounded-lg border border-astra-border bg-astra-surface-alt p-3"
              >
                <Monitor className="h-4 w-4 shrink-0 text-slate-500" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-slate-200 truncate">
                    {s.provider.toUpperCase()} · {s.ip_address || 'Unknown IP'}
                  </div>
                  <div className="text-[10px] text-slate-500 truncate">
                    {s.user_agent || 'Unknown device'} · {s.created_at ? new Date(s.created_at).toLocaleString() : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Password Change ── */}
      <div className={card}>
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15">
            <Key className="h-4 w-4 text-amber-400" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-100">Change Password</h2>
            <p className="text-xs text-slate-500">For local authentication only</p>
          </div>
        </div>

        <div className="space-y-3">
          <input
            type="password"
            value={oldPw}
            onChange={e => setOldPw(e.target.value)}
            className={inputClass}
            placeholder="Current password"
          />
          <input
            type="password"
            value={newPw}
            onChange={e => setNewPw(e.target.value)}
            className={inputClass}
            placeholder="New password (min 8 characters)"
          />
          {pwMsg && <p className="text-xs text-slate-400">{pwMsg}</p>}
          <button
            onClick={async () => {
              try {
                await api.post('/auth/change-password', {
                  old_password: oldPw, new_password: newPw,
                });
                setPwMsg('Password changed successfully');
                setOldPw('');
                setNewPw('');
              } catch (err: any) {
                setPwMsg(err.response?.data?.detail || 'Failed to change password');
              }
            }}
            disabled={!oldPw || newPw.length < 8}
            className={btnPrimary}
          >
            Update Password
          </button>
        </div>
      </div>
    </div>
  );
}
