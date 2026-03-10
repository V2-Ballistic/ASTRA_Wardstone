'use client';

export default function SettingsPage() {
  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight">Settings</h1>
      <p className="mb-6 text-sm text-slate-500">PROJ-ALPHA · Project and system configuration</p>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Project Settings */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Project Configuration</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Project Code</label>
              <input defaultValue="PROJ-ALPHA" className="w-full rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Project Name</label>
              <input defaultValue="ASTRA Systems Engineering Platform" className="w-full rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Description</label>
              <textarea defaultValue="Requirements tracking, traceability, and systems engineering management platform." rows={3}
                className="w-full rounded-lg border border-astra-border-light bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50" />
            </div>
          </div>
        </div>

        {/* Quality Settings */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Quality Check Configuration</h2>
          <div className="space-y-3">
            {[
              { label: 'Enforce SHALL/WILL/SHOULD keywords', enabled: true },
              { label: 'Flag prohibited ambiguous terms (NASA App. C)', enabled: true },
              { label: 'Detect compound requirements', enabled: true },
              { label: 'Require rationale for every requirement', enabled: false },
              { label: 'Block baselining with TBD values', enabled: true },
              { label: 'Minimum quality score for approval', enabled: false },
            ].map((setting) => (
              <div key={setting.label} className="flex items-center justify-between rounded-lg border border-astra-border px-4 py-3">
                <span className="text-xs text-slate-300">{setting.label}</span>
                <div className={`h-5 w-9 rounded-full p-0.5 transition-colors cursor-pointer ${
                  setting.enabled ? 'bg-blue-500' : 'bg-slate-600'
                }`}>
                  <div className={`h-4 w-4 rounded-full bg-white transition-transform ${
                    setting.enabled ? 'translate-x-4' : 'translate-x-0'
                  }`} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Database Info */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">System Information</h2>
          <div className="space-y-2 font-mono text-xs">
            {[
              ['API', 'http://localhost:8000'],
              ['Database', 'PostgreSQL 16'],
              ['pgAdmin', 'http://localhost:5050'],
              ['Frontend', 'Next.js 14 / React 18'],
              ['Backend', 'FastAPI / Python 3.12'],
              ['Version', 'ASTRA v1.0.0'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-astra-border py-2 last:border-0">
                <span className="text-slate-500">{k}</span>
                <span className="text-slate-300">{v}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Team */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-6">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Team Members</h2>
          {[
            { name: 'J. Martinez', role: 'Requirements Engineer', initials: 'JM', color: 'from-blue-500 to-violet-500' },
            { name: 'K. Chen', role: 'Systems Architect', initials: 'KC', color: 'from-emerald-500 to-cyan-500' },
            { name: 'R. Patel', role: 'Project Manager', initials: 'RP', color: 'from-orange-500 to-pink-500' },
            { name: 'A. Nowak', role: 'QA Engineer', initials: 'AN', color: 'from-violet-500 to-fuchsia-500' },
            { name: 'M. Torres', role: 'DevOps Lead', initials: 'MT', color: 'from-cyan-500 to-blue-500' },
          ].map((m) => (
            <div key={m.name} className="flex items-center gap-3 border-b border-astra-border py-3 last:border-0">
              <div className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${m.color} text-[11px] font-bold text-white`}>
                {m.initials}
              </div>
              <div>
                <div className="text-xs font-semibold text-slate-200">{m.name}</div>
                <div className="text-[10px] text-slate-500">{m.role}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
