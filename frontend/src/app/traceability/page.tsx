'use client';

export default function TraceabilityPage() {
  const nodes = [
    { id: 'stakeholder', label: 'Stakeholder Need', x: 40, y: 45, color: '#8B5CF6' },
    { id: 'source', label: 'Source Artifact', x: 40, y: 160, color: '#F59E0B' },
    { id: 'sysreq', label: 'System Requirement', x: 260, y: 100, color: '#3B82F6' },
    { id: 'subreq', label: 'Sub-System Req', x: 480, y: 50, color: '#3B82F6' },
    { id: 'design', label: 'Design Element', x: 480, y: 155, color: '#06B6D4' },
    { id: 'test', label: 'Test Case', x: 680, y: 100, color: '#10B981' },
  ];
  const edges = [
    ['stakeholder', 'sysreq'], ['source', 'sysreq'],
    ['sysreq', 'subreq'], ['sysreq', 'design'],
    ['subreq', 'test'], ['design', 'test'],
  ];

  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight">Traceability Matrix</h1>
      <p className="mb-6 text-sm text-slate-500">PROJ-ALPHA · Full lifecycle traceability chain</p>

      {/* Graph */}
      <div className="mb-6 rounded-xl border border-astra-border bg-astra-surface p-6">
        <h2 className="mb-4 text-sm font-bold text-slate-200">Traceability Graph — Full Lifecycle Chain</h2>
        <svg width="100%" height="220" viewBox="0 0 800 220" className="overflow-visible">
          {edges.map(([from, to], i) => {
            const a = nodes.find(n => n.id === from)!;
            const b = nodes.find(n => n.id === to)!;
            return <line key={i} x1={a.x + 60} y1={a.y + 18} x2={b.x} y2={b.y + 18}
              stroke="#2A3548" strokeWidth="2" strokeDasharray="6 3" />;
          })}
          {nodes.map(n => (
            <g key={n.id}>
              <rect x={n.x} y={n.y} width={120} height={36} rx="8"
                fill={n.color + '18'} stroke={n.color} strokeWidth="1.5" />
              <text x={n.x + 60} y={n.y + 22} textAnchor="middle"
                fill={n.color} fontSize="11" fontWeight="600" fontFamily="DM Sans, sans-serif">
                {n.label}
              </text>
            </g>
          ))}
        </svg>
        <div className="mt-3 text-xs text-slate-500">← Pre-RS Traceability | Post-RS Traceability →</div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Coverage */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Coverage Analysis</h2>
          {[
            { label: 'Requirements with Source Artifacts', value: 83, color: '#10B981' },
            { label: 'Requirements with Test Cases', value: 42, color: '#F59E0B' },
            { label: 'Requirements with Design Links', value: 67, color: '#3B82F6' },
            { label: 'Fully Traced (End-to-End)', value: 33, color: '#EF4444' },
          ].map(m => (
            <div key={m.label} className="mb-4">
              <div className="mb-1.5 flex justify-between">
                <span className="text-xs text-slate-400">{m.label}</span>
                <span className="text-xs font-bold" style={{ color: m.color }}>{m.value}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-astra-surface-alt">
                <div className="h-full rounded-full" style={{ width: `${m.value}%`, background: m.color }} />
              </div>
            </div>
          ))}
        </div>

        {/* Issues */}
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h2 className="mb-4 text-sm font-bold text-slate-200">Traceability Issues</h2>
          {[
            { label: 'Orphan Requirements (no parent)', count: 4, sev: 'warning' },
            { label: 'Dead-End Requirements (no children/V&V)', count: 8, sev: 'danger' },
            { label: 'Broken Trace Links', count: 1, sev: 'danger' },
            { label: 'Unverified Baselined Requirements', count: 3, sev: 'warning' },
          ].map((item) => (
            <div key={item.label} className={`mb-2 flex items-center justify-between rounded-lg px-3 py-2.5 ${
              item.sev === 'danger' ? 'bg-red-500/10' : 'bg-yellow-500/10'
            }`}>
              <span className="text-xs text-slate-200">{item.label}</span>
              <span className={`text-sm font-bold ${item.sev === 'danger' ? 'text-red-400' : 'text-yellow-400'}`}>
                {item.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
