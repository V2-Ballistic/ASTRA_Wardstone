'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft, Edit3, Trash2, RotateCcw, Clock, MessageSquare,
  GitBranch, Link2, ChevronRight, Shield, Loader2, Send, Reply,
  AlertTriangle, CheckCircle, X, Check, Copy
} from 'lucide-react';
import { requirementsAPI } from '@/lib/api';
import {
  STATUS_COLORS, STATUS_LABELS, LEVEL_COLORS, LEVEL_LABELS, PRIORITY_COLORS,
  type RequirementStatus, type RequirementLevel, type Priority
} from '@/lib/types';
import { useAuth } from '@/lib/auth';

// ── Quality checker (mirrors backend) ──
const PROHIBITED = ['flexible','easy','sufficient','safe','adequate','accommodate','user-friendly','appropriate','fast','portable','lightweight','maximize','minimize','robust','quickly','easily','clearly','simply','efficiently','effectively','reasonable','etc','and/or','as needed','timely'];
const AMBIGUOUS = ['some','several','many','few','often','usually','generally','normally','approximately','about','significant','minimal','considerable'];
function localQualityScore(s: string, r: string) {
  if (!s || s.trim().length < 10) return { score: 0, passed: false };
  let sc = 100; const t = s.trim(), tl = t.toLowerCase();
  if (!/\bshall\b/i.test(t) && !/\bwill\b/i.test(t) && !/\bshould\b/i.test(t)) sc -= 20;
  if ((t.match(/\bshall\b/gi)||[]).length > 1) sc -= 15;
  const pf = PROHIBITED.filter(x => tl.includes(x.toLowerCase()));
  if (pf.length) sc -= Math.min(5*pf.length,25);
  const af = AMBIGUOUS.filter(x => new RegExp(`\\b${x}\\b`,'i').test(t));
  if (af.length) sc -= Math.min(3*af.length,15);
  if (/\bTBD\b/g.test(t)) sc -= 8;
  if (t.split(/\s+/).length < 5) sc -= 10;
  if (!r || r.trim().length < 5) sc -= 5;
  if (/\bshall\b/i.test(t) && !/\d+/.test(t)) sc -= 5;
  return { score: Math.max(0,Math.min(100,Math.round(sc))), passed: sc >= 70 };
}

const TRANSITIONS: Record<string, string[]> = {
  draft:['under_review','deleted'], under_review:['approved','draft','deleted'],
  approved:['baselined','under_review','deleted'], baselined:['approved','deleted'],
  implemented:['verified','approved','deleted'], verified:['validated','approved','deleted'],
  validated:['approved','deleted'], deferred:['draft','deleted'], deleted:['draft'],
};

function ScoreRing({ score, size = 72 }: { score: number; size?: number }) {
  const color = score >= 90 ? '#10B981' : score >= 70 ? '#F59E0B' : '#EF4444';
  const r = (size-8)/2, circ = 2*Math.PI*r, offset = circ-(score/100)*circ;
  return (<div className="relative" style={{width:size,height:size}}>
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(100,116,139,0.15)" strokeWidth={4}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4} strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-500"/>
    </svg>
    <div className="absolute inset-0 flex items-center justify-center"><span className="text-base font-bold" style={{color}}>{score}</span></div>
  </div>);
}

// ── Inline editable text ──
function EditableText({ label, value, onSave, multiline=false, showQuality=false, rationale='' }: {
  label:string; value:string; onSave:(v:string)=>Promise<void>; multiline?:boolean; showQuality?:boolean; rationale?:string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setDraft(value); }, [value]);
  const liveScore = showQuality ? localQualityScore(draft, rationale) : null;
  const save = async () => {
    if (draft.trim() === value.trim()) { setEditing(false); return; }
    setSaving(true); try { await onSave(draft.trim()); setEditing(false); } catch {} finally { setSaving(false); }
  };
  const cancel = () => { setDraft(value); setEditing(false); };

  if (editing) return (
    <div className="rounded-xl border border-blue-500/30 bg-astra-surface p-5">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-blue-400">{label} — Editing</span>
        {showQuality && liveScore && <span className="text-xs font-bold" style={{color: liveScore.score>=90?'#10B981':liveScore.score>=70?'#F59E0B':'#EF4444'}}>Score: {liveScore.score}</span>}
      </div>
      {multiline
        ? <textarea value={draft} onChange={e=>setDraft(e.target.value)} rows={4} autoFocus className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm leading-relaxed text-slate-200 outline-none focus:border-blue-500/50 resize-none"/>
        : <input value={draft} onChange={e=>setDraft(e.target.value)} autoFocus onKeyDown={e=>{if(e.key==='Enter')save();if(e.key==='Escape')cancel();}} className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-blue-500/50"/>}
      {multiline && <div className="mt-1 text-[10px] text-slate-600">{draft.split(/\s+/).filter(Boolean).length} words</div>}
      <div className="mt-2 flex items-center gap-2 justify-end">
        <button onClick={cancel} className="flex items-center gap-1 rounded-lg border border-astra-border px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200"><X className="h-3 w-3"/> Cancel</button>
        <button onClick={save} disabled={saving} className="flex items-center gap-1 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50">{saving?<Loader2 className="h-3 w-3 animate-spin"/>:<Check className="h-3 w-3"/>} Save</button>
      </div>
    </div>
  );

  return (
    <div className="group rounded-xl border border-astra-border bg-astra-surface p-5 transition hover:border-blue-500/20 cursor-pointer" onClick={()=>setEditing(true)}>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</span>
        <Edit3 className="h-3.5 w-3.5 text-slate-600 opacity-0 transition group-hover:opacity-100 group-hover:text-blue-400"/>
      </div>
      {value ? <p className={`${multiline?'text-[14px] leading-relaxed text-slate-200':'text-lg font-bold leading-snug text-slate-100'}`}>{value}</p>
        : <p className="text-sm italic text-slate-500">Click to add {label.toLowerCase()}</p>}
    </div>
  );
}

// ── Inline editable select (status, type) ──
function EditableSelect({ label, value, options, onSave, colorMap }: {
  label:string; value:string; options:{value:string;label:string}[]; onSave:(v:string)=>Promise<void>; colorMap?:Record<string,{bg:string;text:string}>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const save = async (v: string) => {
    if (v===value){setEditing(false);return;} setSaving(true);setError('');
    try{await onSave(v);setEditing(false);}catch(e:any){setError(e.response?.data?.detail||'Invalid transition');}finally{setSaving(false);}
  };
  const sc = colorMap?.[value];
  if (editing) return (<div>
    <div className="flex items-center justify-between mb-1"><span className="text-[11px] text-blue-400 font-semibold">{label}</span><button onClick={()=>{setEditing(false);setError('');}} className="text-slate-500 hover:text-slate-300"><X className="h-3 w-3"/></button></div>
    <div className="space-y-1">{options.map(o=>{const osc=colorMap?.[o.value];return(
      <button key={o.value} onClick={()=>save(o.value)} disabled={saving} className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition text-left ${o.value===value?'ring-1 ring-blue-500':'hover:bg-astra-surface-hover'}`}>
        {osc&&<div className="h-2 w-2 rounded-full" style={{background:osc.text}}/>}<span className="text-slate-200">{o.label}</span>{o.value===value&&<Check className="ml-auto h-3 w-3 text-blue-400"/>}
      </button>);})}</div>
    {error&&<div className="mt-1 text-[11px] text-red-400">{error}</div>}
  </div>);
  return (<div className="group flex items-center justify-between cursor-pointer" onClick={()=>setEditing(true)}>
    <span className="text-[11px] text-slate-500">{label}</span>
    <div className="flex items-center gap-1.5">
      {sc?<span className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold" style={{background:sc.bg,color:sc.text}}>{options.find(o=>o.value===value)?.label||value}</span>
        :<span className="text-xs font-semibold capitalize text-slate-300">{options.find(o=>o.value===value)?.label||value}</span>}
      <Edit3 className="h-3 w-3 text-slate-600 opacity-0 transition group-hover:opacity-100 group-hover:text-blue-400"/>
    </div>
  </div>);
}

// ── Inline editable button group (priority, level) ──
function EditableButtonGroup({ label, value, options, onSave, colorMap }: {
  label:string; value:string; options:{value:string;label:string}[]; onSave:(v:string)=>Promise<void>; colorMap:Record<string,string>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const save = async (v:string) => {
    if(v===value){setEditing(false);return;} setSaving(true);
    try{await onSave(v);setEditing(false);}catch{}finally{setSaving(false);}
  };
  if (editing) return (<div>
    <div className="flex items-center justify-between mb-1.5"><span className="text-[11px] text-blue-400 font-semibold">{label}</span><button onClick={()=>setEditing(false)} className="text-slate-500 hover:text-slate-300"><X className="h-3 w-3"/></button></div>
    <div className="flex gap-1">{options.map(o=>(<button key={o.value} onClick={()=>save(o.value)} disabled={saving}
      className={`flex-1 rounded-lg py-1.5 text-[10px] font-bold transition ${value===o.value?'text-white':'border border-astra-border text-slate-400 hover:border-blue-500/30'}`}
      style={value===o.value?{background:colorMap[o.value]}:{}}>{o.label}</button>))}</div>
  </div>);
  return (<div className="group flex items-center justify-between cursor-pointer" onClick={()=>setEditing(true)}>
    <span className="text-[11px] text-slate-500">{label}</span>
    <div className="flex items-center gap-1.5"><div className="h-2 w-2 rounded-full" style={{background:colorMap[value]}}/><span className="text-xs font-semibold capitalize" style={{color:colorMap[value]}}>{options.find(o=>o.value===value)?.label||value}</span>
      <Edit3 className="h-3 w-3 text-slate-600 opacity-0 transition group-hover:opacity-100 group-hover:text-blue-400"/></div>
  </div>);
}

function HistoryEntry({ entry }: { entry: any }) {
  const labels: Record<string,string> = {title:'Title',statement:'Statement',rationale:'Rationale',status:'Status',priority:'Priority',level:'Level',req_type:'Type',parent_id:'Parent',quality_score:'Quality Score',created:'Created'};
  const label = labels[entry.field_changed]||entry.field_changed;
  const isCreation = entry.field_changed==='created';
  const isStatus = entry.field_changed==='status';
  return (<div className="flex gap-3 border-b border-astra-border py-3 last:border-0">
    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-astra-surface-alt">
      {isCreation?<CheckCircle className="h-3.5 w-3.5 text-emerald-400"/>:isStatus?<AlertTriangle className="h-3.5 w-3.5 text-amber-400"/>:<Edit3 className="h-3.5 w-3.5 text-blue-400"/>}
    </div>
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2"><span className="text-xs font-semibold text-slate-200">{entry.changed_by}</span><span className="text-[10px] text-slate-500">v{entry.version}</span></div>
      {isCreation?<div className="mt-0.5 text-xs text-slate-400">{entry.change_description}</div>
        :<div className="mt-1"><span className="text-[11px] font-semibold text-slate-400">{label}: </span>
          {entry.old_value&&<span className="text-[11px] text-red-400/70 line-through mr-1">{String(entry.old_value).substring(0,80)}{String(entry.old_value).length>80?'...':''}</span>}
          <span className="text-[11px] text-emerald-400">{String(entry.new_value).substring(0,80)}{String(entry.new_value).length>80?'...':''}</span></div>}
    </div>
    <div className="shrink-0 text-[10px] text-slate-500 whitespace-nowrap">{entry.changed_at?new Date(entry.changed_at).toLocaleString():''}</div>
  </div>);
}

function CommentItem({ comment, onReply }: { comment:any; onReply:(id:number)=>void }) {
  const initials = comment.author_name?comment.author_name.split(' ').map((n:string)=>n[0]).join('').toUpperCase().slice(0,2):'??';
  return (<div className="border-b border-astra-border py-3 last:border-0"><div className="flex items-start gap-3">
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 text-[10px] font-bold text-white">{initials}</div>
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2"><span className="text-xs font-semibold text-slate-200">{comment.author_name}</span>
        {comment.author_role&&<span className="rounded-full bg-astra-surface-alt px-1.5 py-0.5 text-[9px] text-slate-500">{comment.author_role}</span>}
        <span className="text-[10px] text-slate-500">{comment.created_at?new Date(comment.created_at).toLocaleString():''}</span></div>
      <div className="mt-1 text-[13px] leading-relaxed text-slate-300">{comment.content}</div>
      <button onClick={()=>onReply(comment.id)} className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-500 hover:text-blue-400 transition"><Reply className="h-3 w-3"/> Reply</button>
    </div></div></div>);
}

// ══════════════════════════════════════
export default function RequirementDetailPage() {
  const params = useParams(); const router = useRouter(); const { user } = useAuth();
  const reqId = Number(params.id);
  const [req, setReq] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [comments, setComments] = useState<any[]>([]);
  const [children, setChildren] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'history'|'children'|'traces'|'comments'>('history');
  const [commentText, setCommentText] = useState('');
  const [replyTo, setReplyTo] = useState<number|null>(null);
  const [postingComment, setPostingComment] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const fetchData = useCallback(async () => {
    if (!reqId) return; setLoading(true);
    try {
      const [rr,hr,cr] = await Promise.all([requirementsAPI.get(reqId),requirementsAPI.getHistory(reqId),requirementsAPI.getComments(reqId)]);
      setReq(rr.data); setHistory(hr.data.history||[]); setComments(cr.data.comments||[]); setChildren(rr.data.children||[]);
    } catch(e:any){setError(e.response?.data?.detail||'Failed to load');} finally{setLoading(false);}
  }, [reqId]);
  useEffect(()=>{fetchData();},[fetchData]);

  const saveField = async (field:string, value:any) => {
    await requirementsAPI.update(reqId, {[field]:value});
    setSaveMsg(`${field} updated`); setTimeout(()=>setSaveMsg(''),2000);
    const [rr,hr] = await Promise.all([requirementsAPI.get(reqId),requirementsAPI.getHistory(reqId)]);
    setReq(rr.data); setHistory(hr.data.history||[]); setChildren(rr.data.children||[]);
  };

  const handlePostComment = async () => {
    if(!commentText.trim())return; setPostingComment(true);
    try{await requirementsAPI.postComment(reqId,commentText.trim(),replyTo||undefined);setCommentText('');setReplyTo(null);
      const cr=await requirementsAPI.getComments(reqId);setComments(cr.data.comments||[]);
    }catch(e:any){setError(e.response?.data?.detail||'Failed');}finally{setPostingComment(false);}
  };

  const handleDelete = async () => {
    if(!confirm(`Soft-delete ${req.req_id}?`))return;
    try{await requirementsAPI.delete(reqId);router.push('/requirements');}catch(e:any){setError(e.response?.data?.detail||'Failed');}
  };

  const handleDuplicate = async () => {
    try {
      const res = await requirementsAPI.clone(reqId);
      router.push(`/requirements/${res.data.id}`);
    } catch(e:any) { setError(e.response?.data?.detail||'Failed to duplicate'); }
  };

  if(loading) return <div className="flex min-h-[60vh] items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-500"/></div>;
  if(error&&!req) return (<div className="flex min-h-[60vh] flex-col items-center justify-center gap-4">
    <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-6 py-4 text-sm text-red-400">{error}</div>
    <button onClick={()=>router.push('/requirements')} className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600"><ArrowLeft className="h-4 w-4"/> Back</button>
  </div>);
  if(!req) return null;

  const status = (req.status?.value||req.status) as RequirementStatus;
  const level = (req.level?.value||req.level||'L1') as RequirementLevel;
  const priority = (req.priority?.value||req.priority) as Priority;
  const reqType = (req.req_type?.value||req.req_type) as string;
  const sc = STATUS_COLORS[status]; const isDeleted = status==='deleted';
  const allowedStatuses = [status,...(TRANSITIONS[status]||[])];
  const statusOptions = allowedStatuses.map(s=>({value:s,label:STATUS_LABELS[s as RequirementStatus]||s}));
  const typeOptions = [{value:'functional',label:'Functional'},{value:'performance',label:'Performance'},{value:'interface',label:'Interface'},{value:'security',label:'Security'},{value:'safety',label:'Safety'},{value:'environmental',label:'Environmental'},{value:'reliability',label:'Reliability'},{value:'constraint',label:'Constraint'},{value:'maintainability',label:'Maintainability'},{value:'derived',label:'Derived'}];
  const levelOptions = (['L1','L2','L3','L4','L5'] as RequirementLevel[]).map(l=>({value:l,label:l}));
  const priorityOptions = (['critical','high','medium','low'] as Priority[]).map(p=>({value:p,label:p.charAt(0).toUpperCase()+p.slice(1)}));
  const tabs = [{key:'history' as const,label:'History',icon:Clock,count:history.length},{key:'children' as const,label:'Children',icon:GitBranch,count:children.length},{key:'traces' as const,label:'Trace Links',icon:Link2,count:req.trace_count||0},{key:'comments' as const,label:'Comments',icon:MessageSquare,count:comments.length}];
  const topComments = comments.filter(c=>!c.parent_id);
  const repliesMap:Record<number,any[]>={};
  comments.filter(c=>c.parent_id).forEach(c=>{if(!repliesMap[c.parent_id])repliesMap[c.parent_id]=[];repliesMap[c.parent_id].push(c);});

  return (<div className="mx-auto max-w-6xl">
    {/* Header */}
    <div className="mb-6 flex items-center gap-3">
      <button onClick={()=>router.push('/requirements')} className="flex h-9 w-9 items-center justify-center rounded-lg border border-astra-border text-slate-400 transition hover:text-slate-200"><ArrowLeft className="h-4 w-4"/></button>
      <div className="flex-1 min-w-0"><div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-sm font-bold text-blue-400">{req.req_id}</span>
        <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{background:`${LEVEL_COLORS[level]}20`,color:LEVEL_COLORS[level]}}>{level}</span>
        <span className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold" style={{background:sc?.bg,color:sc?.text}}>{STATUS_LABELS[status]||status}</span>
        <span className="text-[11px] text-slate-500">v{req.version}</span>
        {saveMsg&&<span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400 animate-pulse"><CheckCircle className="h-3 w-3"/> {saveMsg}</span>}
      </div></div>
      <div className="flex items-center gap-2">
        {!isDeleted && <button onClick={handleDuplicate}
          className="flex items-center gap-1.5 rounded-lg border border-astra-border px-3 py-2 text-xs font-semibold text-slate-400 transition hover:border-blue-500/30 hover:text-slate-200">
          <Copy className="h-3.5 w-3.5"/> Duplicate
        </button>}
        {isDeleted?<button onClick={async()=>{await requirementsAPI.restore(reqId);fetchData();}} className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 px-3 py-2 text-xs font-semibold text-emerald-400 transition hover:bg-emerald-500/10"><RotateCcw className="h-3.5 w-3.5"/> Restore</button>
          :<button onClick={handleDelete} className="flex items-center gap-1.5 rounded-lg border border-red-500/20 px-3 py-2 text-xs font-semibold text-red-400 transition hover:bg-red-500/10"><Trash2 className="h-3.5 w-3.5"/> Delete</button>}
      </div>
    </div>

    {error&&<div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>}
    {isDeleted&&<div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3"><Trash2 className="h-4 w-4 text-red-400"/><span className="text-sm text-red-300">Deleted. Click Restore to recover.</span></div>}

    {/* 2-column */}
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
      {/* Left */}
      <div className="space-y-4 xl:col-span-2">
        <EditableText label="Title" value={req.title||''} onSave={v=>saveField('title',v)}/>
        <EditableText label="Requirement Statement" value={req.statement||''} onSave={v=>saveField('statement',v)} multiline showQuality rationale={req.rationale||''}/>
        <EditableText label="Rationale" value={req.rationale||''} onSave={v=>saveField('rationale',v)} multiline/>

        {/* Tabs */}
        <div className="rounded-xl border border-astra-border bg-astra-surface">
          <div className="flex border-b border-astra-border">{tabs.map(tab=>{const Icon=tab.icon;return(
            <button key={tab.key} onClick={()=>setActiveTab(tab.key)} className={`flex items-center gap-1.5 px-4 py-3 text-xs font-semibold transition-all border-b-2 ${activeTab===tab.key?'border-blue-500 text-blue-400':'border-transparent text-slate-500 hover:text-slate-300'}`}>
              <Icon className="h-3.5 w-3.5"/> {tab.label} {tab.count>0&&<span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${activeTab===tab.key?'bg-blue-500/20 text-blue-400':'bg-astra-surface-alt text-slate-500'}`}>{tab.count}</span>}
            </button>);})}</div>

          <div className="p-5">
            {activeTab==='history'&&(history.length===0?<div className="py-8 text-center text-sm text-slate-500">No change history yet</div>
              :<div className="max-h-[500px] overflow-y-auto">{history.map(h=><HistoryEntry key={h.id} entry={h}/>)}</div>)}

            {activeTab==='children'&&(children.length===0?<div className="py-8 text-center"><div className="text-sm text-slate-500">No child requirements</div><p className="mt-1 text-xs text-slate-600">Set this as parent when creating a new requirement</p></div>
              :<div className="space-y-1">{children.map((child:any)=>{const cL=(child.level?.value||child.level||'L1') as RequirementLevel;const cS=(child.status?.value||child.status) as RequirementStatus;const cSc=STATUS_COLORS[cS];return(
                <Link key={child.id} href={`/requirements/${child.id}`} className="flex items-center gap-3 rounded-lg p-2.5 transition hover:bg-astra-surface-hover">
                  <span className="rounded-full px-1.5 py-0.5 text-[9px] font-bold" style={{background:`${LEVEL_COLORS[cL]}20`,color:LEVEL_COLORS[cL]}}>{cL}</span>
                  <span className="font-mono text-xs font-semibold text-blue-400">{child.req_id}</span>
                  <span className="flex-1 truncate text-sm text-slate-300">{child.title}</span>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold" style={{background:cSc?.bg,color:cSc?.text}}>{STATUS_LABELS[cS]}</span>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-500"/>
                </Link>);})}</div>)}

            {activeTab==='traces'&&((req.trace_count||0)===0
              ?<div className="py-8 text-center"><div className="text-sm text-slate-500">No trace links</div><p className="mt-1 text-xs text-slate-600">Add from Traceability page</p></div>
              :<div className="py-4 text-center"><div className="text-sm text-slate-400">{req.trace_count} trace link{req.trace_count!==1?'s':''}</div>
                <Link href="/traceability" className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-600"><Link2 className="h-3.5 w-3.5"/> View Traceability</Link></div>)}

            {activeTab==='comments'&&(<div>
              {topComments.length===0&&<div className="py-4 text-center text-sm text-slate-500">No comments yet</div>}
              {topComments.map(c=>(<div key={c.id}><CommentItem comment={c} onReply={id=>setReplyTo(id)}/>
                {repliesMap[c.id]&&<div className="ml-10 border-l-2 border-astra-border pl-3">{repliesMap[c.id].map(r=><CommentItem key={r.id} comment={r} onReply={id=>setReplyTo(id)}/>)}</div>}</div>))}
              <div className="mt-4 border-t border-astra-border pt-4">
                {replyTo&&<div className="mb-2 flex items-center gap-2"><span className="text-[11px] text-slate-500">Replying to #{replyTo}</span><button onClick={()=>setReplyTo(null)} className="text-[11px] text-red-400">Cancel</button></div>}
                <div className="flex gap-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-violet-500 text-[10px] font-bold text-white">{user?.full_name?.split(' ').map(n=>n[0]).join('').toUpperCase().slice(0,2)||'??'}</div>
                  <div className="flex-1">
                    <textarea value={commentText} onChange={e=>setCommentText(e.target.value)} placeholder="Add a comment..." rows={2} className="w-full rounded-lg border border-astra-border bg-astra-surface-alt px-3 py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-500/50 resize-none"/>
                    <div className="mt-2 flex justify-end"><button onClick={handlePostComment} disabled={!commentText.trim()||postingComment} className="flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-40">{postingComment?<Loader2 className="h-3 w-3 animate-spin"/>:<Send className="h-3 w-3"/>} {postingComment?'Posting...':'Post'}</button></div>
                  </div>
                </div>
              </div>
            </div>)}
          </div>
        </div>
      </div>

      {/* Right sidebar */}
      <div className="space-y-4">
        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500"><Shield className="h-3.5 w-3.5 text-blue-400"/> Quality Score</h3>
          <div className="flex items-center justify-center"><ScoreRing score={req.quality_score||0} size={90}/></div>
          <div className="mt-2 text-center text-[11px] text-slate-500">{req.quality_score>=90?'Excellent — NASA Compliant':req.quality_score>=70?'Acceptable':'Needs Improvement'}</div>
        </div>

        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Properties</h3>
          <div className="space-y-4">
            <EditableSelect label="Status" value={status} options={statusOptions} onSave={v=>saveField('status',v)} colorMap={STATUS_COLORS}/>
            <EditableButtonGroup label="Level" value={level} options={levelOptions} onSave={v=>saveField('level',v)} colorMap={LEVEL_COLORS as Record<string,string>}/>
            <EditableSelect label="Type" value={reqType} options={typeOptions} onSave={v=>saveField('req_type',v)}/>
            <EditableButtonGroup label="Priority" value={priority} options={priorityOptions} onSave={v=>saveField('priority',v)} colorMap={PRIORITY_COLORS as Record<string,string>}/>
            <div className="flex items-center justify-between"><span className="text-[11px] text-slate-500">Version</span><span className="font-mono text-xs font-semibold text-slate-300">v{req.version}</span></div>
            {req.parent_id&&<div className="flex items-center justify-between"><span className="text-[11px] text-slate-500">Parent</span><Link href={`/requirements/${req.parent_id}`} className="font-mono text-xs font-semibold text-blue-400 hover:text-blue-300">#{req.parent_id}</Link></div>}
          </div>
        </div>

        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Timeline</h3>
          <div className="space-y-2.5">
            <div><div className="text-[10px] text-slate-500">Created</div><div className="text-xs text-slate-300">{req.created_at?new Date(req.created_at).toLocaleString():'—'}</div></div>
            <div><div className="text-[10px] text-slate-500">Last Modified</div><div className="text-xs text-slate-300">{req.updated_at?new Date(req.updated_at).toLocaleString():'—'}</div></div>
          </div>
        </div>

        <div className="rounded-xl border border-astra-border bg-astra-surface p-5">
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Stats</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center"><div className="text-lg font-bold text-slate-100">{children.length}</div><div className="text-[10px] text-slate-500">Children</div></div>
            <div className="text-center"><div className="text-lg font-bold text-blue-400">{req.trace_count||0}</div><div className="text-[10px] text-slate-500">Trace Links</div></div>
            <div className="text-center"><div className="text-lg font-bold text-slate-100">{history.length}</div><div className="text-[10px] text-slate-500">Changes</div></div>
            <div className="text-center"><div className="text-lg font-bold text-slate-100">{comments.length}</div><div className="text-[10px] text-slate-500">Comments</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>);
}
