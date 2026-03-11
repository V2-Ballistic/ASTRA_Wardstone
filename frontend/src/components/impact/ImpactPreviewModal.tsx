/**
 * ASTRA — Impact Preview Modal
 * ===============================
 * File: frontend/src/components/impact/ImpactPreviewModal.tsx   ← NEW
 *
 * Shown before delete or significant edits.
 * Runs a what-if analysis and requires user acknowledgement
 * if impacts exist. Blocks high/critical changes without a
 * change request acknowledgement.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle, XCircle, Loader2, X, Trash2, Shield,
  FlaskConical, Archive, ChevronDown, ChevronRight,
  AlertOctagon, CheckCircle, Edit3,
} from 'lucide-react';
import { impactAPI, type WhatIfPreview } from '@/lib/impact-api';

interface ImpactPreviewModalProps {
  isOpen: boolean;
  requirementId: number;
  requirementIdentifier: string;
  action: 'delete' | 'modify';
  onConfirm: () => void;
  onCancel: () => void;
}

const RISK_STYLES: Record<string, { bg: string; border: string; text: string; iconColor: string }> = {
  low:      { bg: 'bg-emerald-500/5', border: 'border-emerald-500/20', text: 'text-emerald-400', iconColor: 'text-emerald-400' },
  medium:   { bg: 'bg-amber-500/5', border: 'border-amber-500/20', text: 'text-amber-400', iconColor: 'text-amber-400' },
  high:     { bg: 'bg-orange-500/5', border: 'border-orange-500/20', text: 'text-orange-400', iconColor: 'text-orange-400' },
  critical: { bg: 'bg-red-500/5', border: 'border-red-500/20', text: 'text-red-400', iconColor: 'text-red-400' },
};

export default function ImpactPreviewModal({
  isOpen,
  requirementId,
  requirementIdentifier,
  action,
  onConfirm,
  onCancel,
}: ImpactPreviewModalProps) {
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<WhatIfPreview | null>(null);
  const [error, setError] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  const loadPreview = useCallback(async () => {
    if (!isOpen) return;
    setLoading(true);
    setError('');
    setAcknowledged(false);
    try {
      const res = await impactAPI.whatIf(requirementId, action);
      setPreview(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to analyze impact');
    } finally {
      setLoading(false);
    }
  }, [isOpen, requirementId, action]);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  if (!isOpen) return null;

  const risk = preview ? RISK_STYLES[preview.risk_level] || RISK_STYLES.low : RISK_STYLES.low;
  const isHighRisk = preview?.risk_level === 'high' || preview?.risk_level === 'critical';
  const canProceed = !isHighRisk || acknowledged;
  const actionVerb = action === 'delete' ? 'Delete' : 'Save Changes';
  const ActionIcon = action === 'delete' ? Trash2 : Edit3;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />

      {/* Modal */}
      <div className="relative mx-4 w-full max-w-lg rounded-2xl border border-astra-border bg-astra-bg shadow-2xl shadow-black/40">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-astra-border px-5 py-4">
          <div className="flex items-center gap-3">
            {action === 'delete' ? (
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-500/10">
                <Trash2 className="h-4.5 w-4.5 text-red-400" />
              </div>
            ) : (
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10">
                <Edit3 className="h-4.5 w-4.5 text-amber-400" />
              </div>
            )}
            <div>
              <h2 className="text-sm font-bold text-white">
                {action === 'delete' ? 'Confirm Deletion' : 'Preview Impact'}
              </h2>
              <p className="text-[11px] text-slate-400">
                {requirementIdentifier}
              </p>
            </div>
          </div>
          <button onClick={onCancel} className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-700/50 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="flex flex-col items-center gap-3 py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
              <span className="text-sm text-slate-400">Analyzing impact…</span>
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          ) : preview ? (
            <div className="space-y-4">
              {/* Risk banner */}
              <div className={`rounded-xl border ${risk.border} ${risk.bg} p-3`}>
                <div className="flex items-start gap-2.5">
                  {isHighRisk ? (
                    <AlertOctagon className={`mt-0.5 h-4.5 w-4.5 shrink-0 ${risk.iconColor}`} />
                  ) : (
                    <AlertTriangle className={`mt-0.5 h-4.5 w-4.5 shrink-0 ${risk.iconColor}`} />
                  )}
                  <div>
                    <span className={`text-xs font-bold uppercase ${risk.text}`}>
                      {preview.risk_level} risk
                    </span>
                    <p className="mt-1 text-[12px] leading-relaxed text-slate-300">
                      {preview.ai_summary}
                    </p>
                  </div>
                </div>
              </div>

              {/* Impact counters */}
              <div className="grid grid-cols-3 gap-2">
                <CounterBox label="Direct" value={preview.direct_count} color="text-orange-400" />
                <CounterBox label="Indirect" value={preview.indirect_count} color="text-amber-400" />
                <CounterBox label="Orphaned" value={preview.orphaned_count} color="text-red-400" />
              </div>

              {/* Verification & baseline warnings */}
              {preview.verification_rerun_count > 0 && (
                <div className="flex items-center gap-2 rounded-lg border border-violet-500/20 bg-violet-500/5 px-3 py-2">
                  <FlaskConical className="h-3.5 w-3.5 text-violet-400" />
                  <span className="text-[11px] text-violet-300">
                    {preview.verification_rerun_count} verification(s) will need re-execution
                  </span>
                </div>
              )}
              {preview.baseline_impact_count > 0 && (
                <div className="flex items-center gap-2 rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2">
                  <Archive className="h-3.5 w-3.5 text-sky-400" />
                  <span className="text-[11px] text-sky-300">
                    {preview.baseline_impact_count} baseline(s) contain this requirement
                  </span>
                </div>
              )}

              {/* Orphaned children warning */}
              {preview.orphaned_requirements.length > 0 && (
                <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                  <div className="mb-1 text-[11px] font-semibold text-red-400">
                    Orphaned Children
                  </div>
                  <div className="space-y-1">
                    {preview.orphaned_requirements.map((orphan: any) => (
                      <div key={orphan.id} className="flex items-center gap-2 text-[11px] text-slate-400">
                        <Shield className="h-3 w-3 text-red-400/50" />
                        <span className="font-mono text-blue-400">{orphan.req_id}</span>
                        <span className="truncate">{orphan.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expandable details */}
              {preview.affected_items.length > 0 && (
                <button
                  onClick={() => setShowDetails(!showDetails)}
                  className="flex w-full items-center gap-1.5 text-[11px] text-slate-400 transition hover:text-slate-200"
                >
                  {showDetails ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  View all {preview.total_affected} affected items
                </button>
              )}
              {showDetails && (
                <div className="max-h-40 overflow-y-auto rounded-lg border border-astra-border bg-astra-surface p-2">
                  {preview.affected_items.map((item) => (
                    <div key={`${item.entity_type}-${item.entity_id}`} className="flex items-center gap-2 px-2 py-1 text-[10px]">
                      <span className={item.impact_level === 'direct' ? 'text-orange-400' : 'text-amber-400'}>●</span>
                      <span className="font-mono font-semibold text-blue-400">{item.entity_identifier}</span>
                      <span className="truncate text-slate-500">{item.entity_title}</span>
                      <span className="shrink-0 text-slate-600">{item.hop_count}h</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Recommendation */}
              {preview.recommendation && (
                <div className="rounded-lg border border-slate-700/40 bg-slate-800/30 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
                  {preview.recommendation}
                </div>
              )}

              {/* High-risk acknowledgement */}
              {isHighRisk && (
                <label className="flex items-start gap-2.5 rounded-lg border border-red-500/20 bg-red-500/5 p-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-800 text-red-500 focus:ring-red-500/30"
                  />
                  <span className="text-[11px] leading-relaxed text-red-300">
                    I understand this is a <strong>{preview.risk_level}-risk change</strong> affecting{' '}
                    {preview.total_affected} item(s). I have reviewed the impacts and accept responsibility
                    for this action.
                    {preview.requires_change_request && (
                      <> A formal change request is recommended before proceeding.</>
                    )}
                  </span>
                </label>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-astra-border px-5 py-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs font-semibold text-slate-400 transition hover:bg-astra-surface-hover hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading || !!error || !canProceed}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition disabled:opacity-40 ${
              action === 'delete'
                ? 'bg-red-600 text-white hover:bg-red-500 shadow-lg shadow-red-500/20'
                : 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-500/20'
            }`}
          >
            <ActionIcon className="h-3.5 w-3.5" />
            {actionVerb}
            {preview && preview.total_affected > 0 && (
              <span className="rounded-full bg-white/20 px-1.5 py-0 text-[9px]">
                {preview.total_affected} affected
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}


function CounterBox({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-lg border border-astra-border bg-astra-surface p-2.5 text-center">
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-[9px] text-slate-500">{label}</div>
    </div>
  );
}
