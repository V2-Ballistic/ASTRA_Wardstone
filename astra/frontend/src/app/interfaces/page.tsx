'use client';

import { MonitorDot, FileText, Network, Zap, GitBranch, Shield } from 'lucide-react';

const FEATURES = [
  { title: 'Interface Control Documents', desc: 'Create and manage ICDs following NASA Appendix L format with structured interface requirements.', icon: FileText, status: 'Planned' },
  { title: 'Interface Matrix', desc: 'Visual N×N matrix showing all system interfaces, their protocols, data formats, and compliance status.', icon: Network, status: 'Planned' },
  { title: 'API Documentation', desc: 'Auto-generated OpenAPI 3.0 specs linked to interface requirements with live endpoint testing.', icon: Zap, status: 'Planned' },
  { title: 'Integration Readiness', desc: 'Track interface readiness levels across system boundaries with dependency visualization.', icon: GitBranch, status: 'Planned' },
  { title: 'Data Flow Diagrams', desc: 'Interactive system context and data flow diagrams with drag-and-drop editing.', icon: MonitorDot, status: 'Planned' },
  { title: 'Standard Compliance', desc: 'Map interfaces to ITS standards (NTCIP, TMDD) and track compliance per FHWA 940.11.', icon: Shield, status: 'Planned' },
];

export default function InterfacesPage() {
  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight">System Interfaces</h1>
      <p className="mb-6 text-sm text-slate-500">PROJ-ALPHA · Interface management and integration</p>

      <div className="mb-8 rounded-xl border border-astra-border bg-astra-surface p-10 text-center">
        <MonitorDot className="mx-auto mb-4 h-12 w-12 text-slate-600" />
        <h2 className="text-xl font-bold text-slate-200">Interfaces Module</h2>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-slate-500">
          Design, manage, and test system interfaces. Define ICDs, track interface agreements,
          and monitor integration status across all system boundaries.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {FEATURES.map((f) => {
          const Icon = f.icon;
          return (
            <div key={f.title} className="rounded-xl border-l-[3px] border-l-blue-500 border border-astra-border bg-astra-surface p-5">
              <div className="mb-3 flex items-center gap-2.5">
                <Icon className="h-4 w-4 text-blue-400" />
                <h3 className="text-[13px] font-bold text-slate-200">{f.title}</h3>
              </div>
              <p className="mb-3 text-xs leading-relaxed text-slate-500">{f.desc}</p>
              <span className="inline-block rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-blue-400">{f.status}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
