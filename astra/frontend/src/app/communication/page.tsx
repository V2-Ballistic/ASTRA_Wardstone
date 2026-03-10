'use client';

import { MessageSquare, BookOpen, GitPullRequest, Bell, ClipboardList, Activity } from 'lucide-react';

const FEATURES = [
  { title: 'Artifact-Linked Discussions', desc: 'Every conversation thread is linked to a requirement, interface, or design artifact for full traceability.', icon: MessageSquare, status: 'Planned' },
  { title: 'Decision Records', desc: 'Structured decision logging with rationale, alternatives considered, and stakeholder sign-off.', icon: BookOpen, status: 'Planned' },
  { title: 'Review Workflows', desc: 'Formal review cycles with reviewer assignment, comment resolution tracking, and approval gates.', icon: GitPullRequest, status: 'Planned' },
  { title: 'Stakeholder Notifications', desc: 'Configurable alerts when linked artifacts change, reviews are requested, or decisions need input.', icon: Bell, status: 'Planned' },
  { title: 'Meeting Minutes', desc: 'Capture meeting notes as source artifacts with automatic linking to discussed requirements.', icon: ClipboardList, status: 'Planned' },
  { title: 'Activity Feed', desc: 'Real-time project activity stream with filtering by artifact type, team member, or timeframe.', icon: Activity, status: 'Planned' },
];

export default function CommunicationPage() {
  return (
    <div>
      <h1 className="mb-1 text-xl font-bold tracking-tight">Communication Hub</h1>
      <p className="mb-6 text-sm text-slate-500">PROJ-ALPHA · Team collaboration and decision tracking</p>

      <div className="mb-8 rounded-xl border border-astra-border bg-astra-surface p-10 text-center">
        <MessageSquare className="mx-auto mb-4 h-12 w-12 text-slate-600" />
        <h2 className="text-xl font-bold text-slate-200">Communication Module</h2>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-slate-500">
          Centralized communication for engineering teams. Threaded discussions linked to artifacts,
          decision logging, and stakeholder notifications — all traceable.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {FEATURES.map((f) => {
          const Icon = f.icon;
          return (
            <div key={f.title} className="rounded-xl border-l-[3px] border-l-violet-500 border border-astra-border bg-astra-surface p-5">
              <div className="mb-3 flex items-center gap-2.5">
                <Icon className="h-4 w-4 text-violet-400" />
                <h3 className="text-[13px] font-bold text-slate-200">{f.title}</h3>
              </div>
              <p className="mb-3 text-xs leading-relaxed text-slate-500">{f.desc}</p>
              <span className="inline-block rounded-full bg-violet-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-violet-400">{f.status}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
