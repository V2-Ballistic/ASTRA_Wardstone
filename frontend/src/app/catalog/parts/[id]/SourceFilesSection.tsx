'use client';

/**
 * ASTRA — Catalog Part Source Files section.
 * CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2 §2.5.
 *
 * Renders the source CAD files (SLDPRT / SLDASM / STEP) attached to a
 * catalog_part as download buttons. Hidden when no source files
 * exist (legacy rows or pre-Phase-2 imports). Reuses the auth-token
 * shape from the rest of the catalog API client — same axios
 * interceptor attaches the Bearer token.
 */

import { useEffect, useState } from 'react';
import { Download, FileBox, Loader2 } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import api from '@/lib/api';

type SourceFile = {
  kind: 'sldprt' | 'sldasm' | 'step';
  filename: string;
  size_bytes: number;
  sha256: string;
  mime_type: string;
  download_url: string;
};

const KIND_LABEL: Record<SourceFile['kind'], string> = {
  sldprt: 'SLDPRT',
  sldasm: 'SLDASM',
  step:   'STEP',
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function SourceFilesSection({ partId }: { partId: number }) {
  const [files, setFiles] = useState<SourceFile[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    catalogAPI.listPartSourceFiles(partId)
      .then((r) => {
        if (!alive) return;
        setFiles(r.data as SourceFile[]);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [partId]);

  if (loading) return null;
  if (error) return null;
  if (!files || files.length === 0) return null;

  const handleDownload = async (f: SourceFile) => {
    setDownloading(f.kind);
    try {
      const r = await api.get(f.download_url, { responseType: 'blob' });
      const blob = new Blob([r.data as BlobPart], { type: f.mime_type });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = f.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('source-file download failed', e);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section className="rounded-xl border border-astra-border bg-astra-surface p-4 lg:col-span-2">
      <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
        <FileBox className="h-3.5 w-3.5" aria-hidden="true" />
        Source CAD Files ({files.length})
      </h2>
      <div className="flex flex-wrap gap-2">
        {files.map((f) => (
          <button
            key={f.kind}
            type="button"
            onClick={() => handleDownload(f)}
            disabled={downloading === f.kind}
            className="flex items-center gap-2 rounded-md border border-astra-border bg-astra-bg px-3 py-2 text-xs text-slate-200 hover:border-blue-500/40 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {downloading === f.kind ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            <span className="font-semibold">Download {KIND_LABEL[f.kind]}</span>
            <span className="font-mono text-[10px] text-slate-500">
              {fmtBytes(f.size_bytes)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
