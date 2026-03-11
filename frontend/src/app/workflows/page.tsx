'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, CheckCircle, XCircle, Clock, Shield,
  Loader2, Lock, User as UserIcon, ChevronRight,
  Eye, PenLine, AlertTriangle, FileSignature,
} from 'lucide-react';
import api from '@/lib/api';

interface StageDetail {
  stage_number: number;
  name: string;
  description: string;
  required_role: string | null;
  required_count: number;
  require_signature: boolean;
  timeout_hours: number;
  status: string;
  approval_count: number;
  rejection_count: number;
  actions: {
    id: number;
    user_id: number;
    user_full_name: string;
    user_role: string | null;
    action: string;
    comment: string;
    signature_id: number | null;
    acted_at: string | null;
  }[];
}

interface InstanceDetail {
  id: number;
  workflow_name: string | null;
  entity_type: string;
  entity_id: number;
  project_id: number;
  status: string;
  current_stage_number: number;
  submitted_by: string;
  submitted_at: string | null;
  completed_at: string | null;
  stages: StageDetail[];
}

const STATUS_STYLE: Record<string, { bg: string; text: string; icon: any }> = {
  approved:    { bg: 'bg-emerald-500/15', text: 'text-emerald-400', icon: CheckCircle },
  rejected:    { bg: 'bg-red-500/15',     text: 'text-red-400',     icon: XCircle },
  in_progress: { bg: 'bg-blue-500/15',    text: 'text-blue-400',    icon: Clock },
  pending:     { bg: 'bg-slate-500/15',   text: 'text-slate-400',   icon: Clock },
  cancelled:   { bg: 'bg-slate-500/15',   text: 'text-slate-400',   icon: XCircle },
  timed_out:   { bg: 'bg-amber-500/15',   text: 'text-amber-400',   icon: AlertTriangle },
};

const STAGE_STATUS_STYLE: Record<string, { color: string; ring: string }> = {
  completed: { color: '#10B981', ring: 'ring-emerald-500/30' },
  active:    { color: '#3B82F6', ring: 'ring-blue-500/30' },
  rejected:  { color: '#EF4444', ring: 'ring-red-500/30' },
  waiting:   { color: '#475569', ring: 'ring-slate-500/20' },
  timed_out: { color: '#F59E0B', ring: 'ring-amber-500/30' },
};

export default function WorkflowInstancePage() {
  const params = useParams();
  const router = useRouter();
  const instanceId = Number(params.id);

  const [detail, setDetail] = useState<InstanceDetail | null>(null);
  const [loading, setLoading] = useState(true);

  // Signature modal
  const [sigModalOpen, setSigModalOpen] = useState(false);
  const [sigAction, setSigAction] = useState<'approved' | 'rejected'>('approved');
  const [sigPassword, setSigPassword] = useState('');
  const [sigComment, setSigComment] = useState('');
  const [sigSubmitting, setSigSubmitting] = useState(false);
  const [sigError, setSigError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/workflows/instances/${instanceId}`);
      setDetail(r.data);
    } catch { /* ignore */ }
    setLoading(false);
  }, [instanceId]);

  useEffect(() => { load(); }, [load]);

  const openSignModal = (action: 'approved' | 'rejected') => {
    setSigAction(action);
    setSigPassword('');
    setSigComment('');
    setSigError('');
    setSigModalOpen(true);
  };

  const submitAction = async () => {
    setSigSubmitting(true);
    setSigError('');
    try {
      await api.post(`/workflows/instances/${instanceId}/action`, {
        action: sigAction,
        password: sigPassword,
        comment: sigComment,
      });
      setSigModalOpen(false);
      load();
    } catch (e: any) {
      setSigError(e.response?.data?.detail || 'Action failed');
    }
    setSigSubmitting(false);
  };

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="py-20 text-center text-sm text-slate-500">Workflow instance not found</div>
    );
  }

  const st = STATUS_STYLE[detail.status] || STATUS_STYLE.pending;
  const StatusIcon = st.icon;

  const inputClass = 'w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/25';

  return (
    <div className="mx-auto max-w-4xl">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <button onClick={() => router.back()}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold tracking-tight">{detail.workflow_name || 'Workflow'}</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            {detail.entity_type} #{detail.entity_id} · Submitted by {detail.submitted_by}
            {detail.submitted_at && ` · ${new Date(detail.submitted_at).toLocaleDateString()}`}
          </p>
        </div>
        <div className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${st.bg} ${st.text}`}>
          <StatusIcon className="h-3.5 w-3.5" />
          {detail.status.replace('_', ' ').toUpperCase()}
        </div>
      </div>

      {/* Stage progress bar */}
      <div className="mb-8 rounded-xl border border-astra-border bg-astra-surface p-6">
        <div className="flex items-center justify-between mb-4">
          {detail.stages.map((stage, i) => {
            const ss = STAGE_STATUS_STYLE[stage.status] || STAGE_STATUS_STYLE.waiting;
            const isLast = i === detail.stages.length - 1;
            return (
              <div key={i} className="flex items-center flex-1">
                <div className="flex flex-col items-center">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-full ring-2 ${ss.ring}`}
                    style={{ background: ss.color + '20' }}>
                    {stage.status === 'completed'
                      ? <CheckCircle className="h-5 w-5" style={{ color: ss.color }} />
                      : stage.status === 'rejected'
                        ? <XCircle className="h-5 w-5" style={{ color: ss.color }} />
                        : stage.status === 'active'
                          ? <PenLine className="h-4 w-4" style={{ color: ss.color }} />
                          : <Clock className="h-4 w-4" style={{ color: ss.color }} />}
                  </div>
                  <span className="mt-2 text-[10px] font-bold text-slate-400 text-center leading-tight max-w-[80px]">
                    {stage.name}
                  </span>
                  <span className="mt-0.5 text-[9px] text-slate-600">
                    {stage.approval_count}/{stage.required_count}
                  </span>
                </div>
                {!isLast && (
                  <div className="flex-1 mx-2">
                    <div className="h-0.5 rounded-full" style={{
                      background: stage.status === 'completed' ? '#10B981' : '#1E293B',
                    }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Action buttons (only if in_progress) */}
        {detail.status === 'in_progress' && (
          <div className="flex justify-center gap-3 pt-2 border-t border-astra-border mt-4">
            <button onClick={() => openSignModal('approved')}
              className="flex items-center gap-2 rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-white transition hover:bg-emerald-600">
              <FileSignature className="h-4 w-4" /> Approve &amp; Sign
            </button>
            <button onClick={() => openSignModal('rejected')}
              className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-5 py-2 text-sm font-semibold text-red-400 transition hover:bg-red-500/20">
              <XCircle className="h-4 w-4" /> Reject
            </button>
          </div>
        )}
      </div>

      {/* Stage detail cards */}
      <div className="space-y-4">
        {detail.stages.map((stage, i) => {
          const ss = STAGE_STATUS_STYLE[stage.status] || STAGE_STATUS_STYLE.waiting;
          return (
            <div key={i} className="rounded-xl border border-astra-border bg-astra-surface p-5"
              style={{ borderLeftColor: ss.color, borderLeftWidth: 3 }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="text-xs font-bold text-slate-400">Stage {stage.stage_number}</span>
                  <span className="text-sm font-bold text-slate-200">{stage.name}</span>
                  {stage.require_signature && <Lock className="h-3 w-3 text-amber-400" title="E-Signature required" />}
                </div>
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                  style={{ background: ss.color + '20', color: ss.color }}>
                  {stage.status}
                </span>
              </div>

              {stage.description && (
                <p className="mb-3 text-xs text-slate-500">{stage.description}</p>
              )}

              <div className="flex gap-6 mb-3 text-[11px] text-slate-500">
                {stage.required_role && <span>Role: <b className="text-slate-300">{stage.required_role.replace('_', ' ')}</b></span>}
                <span>Needed: <b className="text-slate-300">{stage.required_count}</b></span>
                {stage.timeout_hours > 0 && <span>Timeout: <b className="text-slate-300">{stage.timeout_hours}h</b></span>}
              </div>

              {/* Actions taken at this stage */}
              {stage.actions.length > 0 ? (
                <div className="space-y-1.5">
                  {stage.actions.map(a => (
                    <div key={a.id} className="flex items-center gap-2.5 rounded-lg bg-astra-surface-alt p-2.5">
                      {a.action === 'approved'
                        ? <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        : a.action === 'rejected'
                          ? <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                          : <Eye className="h-3.5 w-3.5 text-blue-400 shrink-0" />}
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold text-slate-200">{a.user_full_name}</span>
                        {a.user_role && <span className="ml-1.5 text-[10px] text-slate-500">{a.user_role.replace('_', ' ')}</span>}
                        {a.comment && <p className="mt-0.5 text-[11px] text-slate-400 truncate">{a.comment}</p>}
                      </div>
                      {a.signature_id && <Shield className="h-3 w-3 text-amber-400 shrink-0" title="Electronically signed" />}
                      <span className="text-[10px] text-slate-600 whitespace-nowrap">
                        {a.acted_at ? new Date(a.acted_at).toLocaleString() : ''}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-slate-600 italic">No actions yet</p>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Electronic Signature Modal ── */}
      {sigModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-astra-border bg-astra-surface p-6 shadow-2xl">
            <div className="mb-4 flex items-center gap-2.5">
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                sigAction === 'approved' ? 'bg-emerald-500/15' : 'bg-red-500/15'
              }`}>
                <FileSignature className={`h-5 w-5 ${
                  sigAction === 'approved' ? 'text-emerald-400' : 'text-red-400'
                }`} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-100">Electronic Signature</h3>
                <p className="text-xs text-slate-500">
                  {sigAction === 'approved'
                    ? 'Confirm your approval with password verification'
                    : 'Confirm your rejection with password verification'}
                </p>
              </div>
            </div>

            <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-300/80 leading-relaxed">
              <b>Non-repudiation notice:</b> By entering your password you are creating a
              legally-binding electronic signature per 21 CFR Part 11.  This action is
              recorded in the tamper-evident audit log and cannot be undone.
            </div>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Re-enter your password
                </label>
                <input type="password" value={sigPassword}
                  onChange={e => setSigPassword(e.target.value)}
                  className={inputClass} placeholder="Your account password" autoFocus />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  Comment (optional)
                </label>
                <textarea value={sigComment} onChange={e => setSigComment(e.target.value)}
                  className={inputClass + ' h-20 resize-none'} placeholder="Add a note…" />
              </div>

              {sigError && (
                <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  {sigError}
                </div>
              )}

              <div className="flex gap-2 pt-1">
                <button onClick={() => setSigModalOpen(false)}
                  className="flex-1 rounded-lg border border-astra-border py-2.5 text-sm font-semibold text-slate-400 transition hover:text-slate-200">
                  Cancel
                </button>
                <button onClick={submitAction} disabled={sigSubmitting || !sigPassword}
                  className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white transition ${
                    sigAction === 'approved' ? 'bg-emerald-500 hover:bg-emerald-600' : 'bg-red-500 hover:bg-red-600'
                  } disabled:opacity-50`}>
                  {sigSubmitting
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <FileSignature className="h-4 w-4" />}
                  Sign &amp; {sigAction === 'approved' ? 'Approve' : 'Reject'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
