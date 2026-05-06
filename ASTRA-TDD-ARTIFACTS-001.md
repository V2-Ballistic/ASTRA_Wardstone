# ASTRA-TDD-ARTIFACTS-001 — Source Artifacts Module (Full UI + Backend Completion)

**Version:** 1.0
**Status:** Specification — ready for Claude Code execution
**Owner:** Mason (Systems Engineering)
**Branch:** `feat/source-artifacts-module` (create from `main`)
**Estimated effort:** ~45 minutes for Claude Code; 3 file groups (backend, frontend, integration)

---

## 1. Purpose

The L0 (Customer/Contractual) requirement level shipped in `ASTRA-TDD-LEVELS-001` requires every L0 requirement to link to a Source Artifact (MRD, SOW, contract clause, etc.). The data model (`SourceArtifact` ORM, `ArtifactType` enum) and basic backend endpoints (`GET/POST /artifacts/`) already exist, but **no UI exists for managing them**, blocking practical L0 use.

This TDD completes the Source Artifacts module:
- Augments backend with missing CRUD operations (GET single, UPDATE, DELETE, file upload, statistics)
- Builds the full frontend UI (list page, detail page, create/edit forms, file upload)
- Adds sidebar navigation
- Wires the L0 requirement form's artifact picker to the API
- Adds the "requirements derived from this artifact" relationship view
- Integrates with the existing audit trail

After this lands, users can manage source artifacts entirely through the UI and L0 reqs are usable end-to-end.

## 2. Discovery (Claude Code: run these first)

Before implementing, inventory the current state. Some pieces may already exist beyond what this TDD assumes:

```bash
# Backend — list current artifact-related code
grep -rn "SourceArtifact\|artifact_router\|/artifacts/" backend/app/ --include="*.py"

# Frontend — find any partial UI or imports
grep -rn "SourceArtifact\|artifacts" frontend/src/ --include="*.tsx" --include="*.ts"

# Confirm the sidebar location
cat frontend/src/components/layout/Sidebar.tsx 2>/dev/null || \
  find frontend/src -name "Sidebar*.tsx" -exec cat {} \;

# Confirm the requirement form location and current artifact picker behavior
grep -rn "source_artifact_id\|sourceArtifact" frontend/src/ --include="*.tsx"
```

**Report findings before making changes.** If any file paths in this TDD don't match reality (different sidebar component, different requirement form path, etc.), adapt accordingly.

## 3. Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Module location | Project-scoped at `/projects/[id]/artifacts` | Matches existing pattern (requirements, interfaces, parts) |
| Sidebar group | **ENGINEERING** group | Source artifacts are engineering reference material |
| Sidebar position | Below "Requirements", above "Traceability" | Logical grouping with related concepts |
| File upload | **Optional** (artifact can exist without attached file) | Some artifacts are just metadata pointers (e.g., contract clause references) |
| File storage | `backend/uploads/artifacts/{project_code}/{artifact_id}/` | Mirrors existing upload pattern |
| Max file size | 50 MB (matches existing `MAX_UPLOAD_BYTES`) | Consistent with system limits |
| Allowed file types | PDF, DOCX, XLSX, TXT, MD, PNG, JPG | Most common contract/spec doc formats |
| Edit permissions | Same as Requirements (RBAC: admin, PM, requirements_engineer can create/edit; reviewer/stakeholder/developer read-only) | Uniform with existing model |
| Delete behavior | **Soft delete** with cascade check — refuse if any L0 requirements still reference it | Protects audit trail integrity |
| Artifact ID generation | Auto-generated as `ART-{project_code}-{NNN}` (already exists) | Keep existing pattern |
| Audit trail | Every create/update/delete recorded via `record_event` | Consistent with existing audit philosophy |
| Search/filter | By type, date range, free-text title search | Standard list-page UX |
| Stats per artifact | Count of L0 requirements linked, last-updated timestamp | Visible at a glance on the list page |

---

## 4. Backend implementation

### 4.1 Augment `backend/app/routers/projects.py` artifacts_router

The existing router has only `GET /` (list) and `POST /` (create). Add the missing endpoints.

**Find the existing artifacts_router section** (search for `artifacts_router = APIRouter`) and replace the entire artifacts section with:

```python
# ══════════════════════════════════════
#  Source Artifacts
# ══════════════════════════════════════

artifacts_router = APIRouter(prefix="/artifacts", tags=["Source Artifacts"])


@artifacts_router.get("/", response_model=List[SourceArtifactResponse])
def list_artifacts(
    project_id: int,
    artifact_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List source artifacts for a project, with optional type filter and search."""
    q = db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id)
    if artifact_type:
        q = q.filter(SourceArtifact.artifact_type == artifact_type)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (SourceArtifact.title.ilike(like)) |
            (SourceArtifact.artifact_id.ilike(like)) |
            (SourceArtifact.description.ilike(like))
        )
    return q.order_by(SourceArtifact.created_at.desc()).all()


@artifacts_router.get("/stats", response_model=List[dict])
def list_artifacts_with_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List artifacts with per-artifact statistics (linked requirement counts)."""
    artifacts = db.query(SourceArtifact).filter(
        SourceArtifact.project_id == project_id
    ).order_by(SourceArtifact.created_at.desc()).all()

    results = []
    for a in artifacts:
        l0_count = db.query(func.count(Requirement.id)).filter(
            Requirement.source_artifact_id == a.id,
            Requirement.level == "L0",
        ).scalar() or 0
        total_reqs = db.query(func.count(Requirement.id)).filter(
            Requirement.source_artifact_id == a.id,
        ).scalar() or 0
        results.append({
            "id": a.id,
            "artifact_id": a.artifact_id,
            "title": a.title,
            "artifact_type": (
                a.artifact_type.value if hasattr(a.artifact_type, "value")
                else str(a.artifact_type)
            ),
            "description": a.description,
            "file_path": a.file_path,
            "source_date": a.source_date.isoformat() if a.source_date else None,
            "participants": a.participants or [],
            "project_id": a.project_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "l0_requirement_count": l0_count,
            "total_requirement_count": total_reqs,
        })
    return results


@artifacts_router.get("/{artifact_id}", response_model=SourceArtifactResponse)
def get_artifact(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single artifact by ID."""
    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")
    return artifact


@artifacts_router.get("/{artifact_id}/requirements", response_model=List[RequirementResponse])
def get_artifact_requirements(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List requirements that reference this artifact."""
    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")

    return db.query(Requirement).filter(
        Requirement.source_artifact_id == artifact_id
    ).order_by(Requirement.level, Requirement.req_id).all()


@artifacts_router.post("/", response_model=SourceArtifactResponse, status_code=201)
def create_artifact(
    project_id: int,
    data: SourceArtifactCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new source artifact."""
    require_role(current_user, ["admin", "project_manager", "requirements_engineer"])

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    count = db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id).count()
    artifact_id_str = f"ART-{project.code}-{count + 1:03d}"
    artifact = SourceArtifact(
        artifact_id=artifact_id_str,
        **data.model_dump(),
        project_id=project_id,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    record_event(
        db, "artifact.created", "source_artifact", artifact.id, current_user.id,
        {"artifact_id": artifact_id_str, "title": artifact.title},
        project_id=project_id, request=request,
    )
    return artifact


@artifacts_router.patch("/{artifact_id}", response_model=SourceArtifactResponse)
def update_artifact(
    project_id: int,
    artifact_id: int,
    data: SourceArtifactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing source artifact."""
    require_role(current_user, ["admin", "project_manager", "requirements_engineer"])

    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")

    changes = {}
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        old_value = getattr(artifact, field, None)
        if old_value != value:
            changes[field] = {"old": str(old_value), "new": str(value)}
            setattr(artifact, field, value)

    if changes:
        db.commit()
        db.refresh(artifact)
        record_event(
            db, "artifact.updated", "source_artifact", artifact.id, current_user.id,
            {"artifact_id": artifact.artifact_id, "changes": changes},
            project_id=project_id, request=request,
        )

    return artifact


@artifacts_router.delete("/{artifact_id}", status_code=204)
def delete_artifact(
    project_id: int,
    artifact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a source artifact. Refuses if any requirements still reference it,
    to protect audit trail integrity. Use the dependency check first.
    """
    require_role(current_user, ["admin", "project_manager"])

    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")

    ref_count = db.query(func.count(Requirement.id)).filter(
        Requirement.source_artifact_id == artifact_id
    ).scalar() or 0
    if ref_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete artifact '{artifact.artifact_id}': "
                f"{ref_count} requirement(s) still reference it. "
                "Update or delete the linked requirements first."
            ),
        )

    record_event(
        db, "artifact.deleted", "source_artifact", artifact.id, current_user.id,
        {"artifact_id": artifact.artifact_id, "title": artifact.title},
        project_id=project_id, request=request,
    )
    db.delete(artifact)
    db.commit()
    return None


@artifacts_router.post("/{artifact_id}/upload", response_model=SourceArtifactResponse)
async def upload_artifact_file(
    project_id: int,
    artifact_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file to attach to a source artifact (PDF, DOCX, etc.)."""
    require_role(current_user, ["admin", "project_manager", "requirements_engineer"])

    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")

    project = db.query(Project).filter(Project.id == project_id).first()

    # Validate extension
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"File type '{ext}' not allowed. Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Build upload path
    upload_dir = os.path.join("uploads", "artifacts", project.code, artifact.artifact_id)
    os.makedirs(upload_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "upload")
    file_path = os.path.join(upload_dir, safe_filename)

    # Write file (size already enforced by BodySizeLimitMiddleware globally)
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Update artifact record
    artifact.file_path = file_path
    db.commit()
    db.refresh(artifact)

    record_event(
        db, "artifact.file_uploaded", "source_artifact", artifact.id, current_user.id,
        {"artifact_id": artifact.artifact_id, "filename": safe_filename, "size_bytes": len(contents)},
        project_id=project_id, request=request,
    )
    return artifact


@artifacts_router.get("/{artifact_id}/download")
def download_artifact_file(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the file attached to a source artifact."""
    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")
    if not artifact.file_path:
        raise HTTPException(404, "No file attached to this artifact")

    import os
    if not os.path.exists(artifact.file_path):
        raise HTTPException(404, "Attached file not found on disk")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=artifact.file_path,
        filename=os.path.basename(artifact.file_path),
        media_type="application/octet-stream",
    )
```

**Required imports** at the top of `projects.py` (add any not already present):
```python
from fastapi import UploadFile, File
from sqlalchemy import func
from app.models import Requirement
from app.schemas import SourceArtifactUpdate, RequirementResponse
```

### 4.2 Add `SourceArtifactUpdate` schema

In `backend/app/schemas/__init__.py`, find the existing Source Artifact schemas section and **add** this new schema:

```python
class SourceArtifactUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    artifact_type: Optional[str] = None
    description: Optional[str] = None
    source_date: Optional[datetime] = None
    participants: Optional[List[str]] = None
```

### 4.3 Add helper for role enforcement (if not already present)

In `backend/app/services/auth.py` (or wherever auth helpers live), check if `require_role` exists. If it doesn't:

```python
def require_role(user: User, allowed_roles: List[str]) -> None:
    """Raise HTTPException 403 if the user's role is not in the allowed list."""
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in allowed_roles and role != "admin":
        raise HTTPException(
            status_code=403,
            detail=f"Operation requires one of roles: {', '.join(allowed_roles)}",
        )
```

(Admins always pass per the global pattern.)

### 4.4 Confirm `Requirement.source_artifact_id` is exposed in response

In `backend/app/schemas/__init__.py`, the `RequirementResponse` should include `source_artifact_id`. If not present, add:
```python
class RequirementResponse(BaseModel):
    ...
    source_artifact_id: Optional[int] = None
```

---

## 5. Frontend implementation

### 5.1 New file: `frontend/src/lib/api/artifacts.ts`

```typescript
/**
 * ASTRA — Source Artifacts API client
 */

import { SourceArtifact } from '@/lib/types';
import { apiClient } from '@/lib/api/client';

export interface SourceArtifactWithStats extends SourceArtifact {
  l0_requirement_count: number;
  total_requirement_count: number;
}

export interface SourceArtifactCreatePayload {
  title: string;
  artifact_type: string;
  description?: string;
  source_date?: string;
  participants?: string[];
}

export interface SourceArtifactUpdatePayload {
  title?: string;
  artifact_type?: string;
  description?: string;
  source_date?: string;
  participants?: string[];
}

export const artifactsApi = {
  list: (projectId: number, filters?: { artifact_type?: string; search?: string }) =>
    apiClient.get<SourceArtifact[]>(
      `/projects/${projectId}/artifacts/`,
      { params: filters }
    ).then(r => r.data),

  listWithStats: (projectId: number) =>
    apiClient.get<SourceArtifactWithStats[]>(
      `/projects/${projectId}/artifacts/stats`
    ).then(r => r.data),

  get: (projectId: number, artifactId: number) =>
    apiClient.get<SourceArtifact>(
      `/projects/${projectId}/artifacts/${artifactId}`
    ).then(r => r.data),

  getRequirements: (projectId: number, artifactId: number) =>
    apiClient.get(
      `/projects/${projectId}/artifacts/${artifactId}/requirements`
    ).then(r => r.data),

  create: (projectId: number, payload: SourceArtifactCreatePayload) =>
    apiClient.post<SourceArtifact>(
      `/projects/${projectId}/artifacts/`,
      payload
    ).then(r => r.data),

  update: (projectId: number, artifactId: number, payload: SourceArtifactUpdatePayload) =>
    apiClient.patch<SourceArtifact>(
      `/projects/${projectId}/artifacts/${artifactId}`,
      payload
    ).then(r => r.data),

  delete: (projectId: number, artifactId: number) =>
    apiClient.delete(
      `/projects/${projectId}/artifacts/${artifactId}`
    ).then(r => r.data),

  uploadFile: (projectId: number, artifactId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<SourceArtifact>(
      `/projects/${projectId}/artifacts/${artifactId}/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ).then(r => r.data);
  },

  downloadFile: (projectId: number, artifactId: number) =>
    apiClient.get(
      `/projects/${projectId}/artifacts/${artifactId}/download`,
      { responseType: 'blob' }
    ).then(r => r.data),
};
```

(Adapt the import path for `apiClient` to whatever the project actually uses — check `frontend/src/lib/api/` for the existing pattern.)

### 5.2 Constants — `frontend/src/lib/types.ts`

Add to the existing `types.ts`:

```typescript
export const ARTIFACT_TYPE_LABELS: Record<ArtifactType, string> = {
  document: 'Document (MRD, SOW, Spec)',
  standard: 'Standard / Specification',
  interview: 'Interview / Meeting Notes',
  meeting: 'Meeting Minutes',
  decision: 'Decision Record',
  legacy: 'Legacy System Reference',
  email: 'Email Correspondence',
  multimedia: 'Multimedia / Recording',
};

export const ARTIFACT_TYPE_ICONS: Record<ArtifactType, string> = {
  document: '📄',
  standard: '📐',
  interview: '🎤',
  meeting: '👥',
  decision: '✅',
  legacy: '🗃️',
  email: '📧',
  multimedia: '🎬',
};

export const ARTIFACT_TYPE_COLORS: Record<ArtifactType, string> = {
  document: '#3B82F6',
  standard: '#8B5CF6',
  interview: '#10B981',
  meeting: '#06B6D4',
  decision: '#F59E0B',
  legacy: '#6B7280',
  email: '#EC4899',
  multimedia: '#EF4444',
};
```

### 5.3 List page — `frontend/src/app/projects/[id]/artifacts/page.tsx`

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Plus, Search, FileText, Filter, Download } from 'lucide-react';
import { artifactsApi, SourceArtifactWithStats } from '@/lib/api/artifacts';
import {
  ArtifactType,
  ARTIFACT_TYPE_LABELS,
  ARTIFACT_TYPE_ICONS,
  ARTIFACT_TYPE_COLORS,
} from '@/lib/types';

export default function ArtifactsListPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [artifacts, setArtifacts] = useState<SourceArtifactWithStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    artifactsApi.listWithStats(projectId)
      .then(data => { if (mounted) setArtifacts(data); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [projectId]);

  const filtered = artifacts.filter(a => {
    if (typeFilter && a.artifact_type !== typeFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        a.title.toLowerCase().includes(s) ||
        a.artifact_id.toLowerCase().includes(s) ||
        (a.description || '').toLowerCase().includes(s)
      );
    }
    return true;
  });

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white mb-1">Source Artifacts</h1>
          <p className="text-sm text-astra-text-dim">
            Documents, standards, and references that requirements trace back to.
          </p>
        </div>
        <button
          onClick={() => router.push(`/projects/${projectId}/artifacts/new`)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Artifact
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-astra-text-dim" />
          <input
            type="text"
            placeholder="Search by title, ID, or description..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-10 pr-3 py-2 bg-astra-surface border border-astra-border rounded-lg text-white placeholder:text-astra-text-dim focus:outline-none focus:border-blue-500"
          />
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="px-3 py-2 bg-astra-surface border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
        >
          <option value="">All Types</option>
          {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Results */}
      {loading ? (
        <div className="text-center py-12 text-astra-text-dim">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 bg-astra-surface border border-astra-border rounded-xl">
          <FileText className="w-12 h-12 mx-auto text-astra-text-dim mb-3" />
          <h3 className="text-white font-medium mb-1">No source artifacts yet</h3>
          <p className="text-sm text-astra-text-dim mb-4">
            Source artifacts capture the origin of requirements (MRDs, SOWs, contract clauses, meeting notes).
          </p>
          <button
            onClick={() => router.push(`/projects/${projectId}/artifacts/new`)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >
            Create the first one
          </button>
        </div>
      ) : (
        <div className="grid gap-3">
          {filtered.map(a => (
            <div
              key={a.id}
              onClick={() => router.push(`/projects/${projectId}/artifacts/${a.id}`)}
              className="p-4 bg-astra-surface border border-astra-border rounded-xl hover:border-blue-500/50 hover:bg-astra-surface-alt cursor-pointer transition-all"
            >
              <div className="flex items-start gap-4">
                <div
                  className="w-12 h-12 rounded-lg flex items-center justify-center text-2xl flex-shrink-0"
                  style={{ backgroundColor: `${ARTIFACT_TYPE_COLORS[a.artifact_type as ArtifactType]}20` }}
                >
                  {ARTIFACT_TYPE_ICONS[a.artifact_type as ArtifactType]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-mono text-astra-text-dim">{a.artifact_id}</span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: `${ARTIFACT_TYPE_COLORS[a.artifact_type as ArtifactType]}20`,
                        color: ARTIFACT_TYPE_COLORS[a.artifact_type as ArtifactType],
                      }}
                    >
                      {ARTIFACT_TYPE_LABELS[a.artifact_type as ArtifactType]}
                    </span>
                  </div>
                  <h3 className="text-white font-medium mb-1 truncate">{a.title}</h3>
                  {a.description && (
                    <p className="text-sm text-astra-text-dim line-clamp-2 mb-2">{a.description}</p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-astra-text-dim">
                    {a.l0_requirement_count > 0 && (
                      <span className="text-red-400">
                        {a.l0_requirement_count} L0 req{a.l0_requirement_count !== 1 ? 's' : ''}
                      </span>
                    )}
                    <span>{a.total_requirement_count} total req{a.total_requirement_count !== 1 ? 's' : ''} traced</span>
                    {a.file_path && (
                      <span className="flex items-center gap-1">
                        <Download className="w-3 h-3" /> File attached
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

### 5.4 Create page — `frontend/src/app/projects/[id]/artifacts/new/page.tsx`

```tsx
'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Save } from 'lucide-react';
import { artifactsApi } from '@/lib/api/artifacts';
import { ArtifactType, ARTIFACT_TYPE_LABELS } from '@/lib/types';

export default function NewArtifactPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);

  const [title, setTitle] = useState('');
  const [artifactType, setArtifactType] = useState<string>('document');
  const [description, setDescription] = useState('');
  const [sourceDate, setSourceDate] = useState('');
  const [participantsText, setParticipantsText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (!title.trim()) { setError('Title is required'); return; }
    setSaving(true);
    setError('');
    try {
      const created = await artifactsApi.create(projectId, {
        title: title.trim(),
        artifact_type: artifactType,
        description: description.trim() || undefined,
        source_date: sourceDate || undefined,
        participants: participantsText
          ? participantsText.split(',').map(s => s.trim()).filter(Boolean)
          : [],
      });

      if (file) {
        await artifactsApi.uploadFile(projectId, created.id, file);
      }

      router.push(`/projects/${projectId}/artifacts/${created.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create artifact');
      setSaving(false);
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-astra-text-dim hover:text-white mb-4 text-sm"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <h1 className="text-2xl font-semibold text-white mb-1">New Source Artifact</h1>
      <p className="text-sm text-astra-text-dim mb-6">
        Document the origin of one or more requirements.
      </p>

      <div className="space-y-4 bg-astra-surface border border-astra-border rounded-xl p-6">
        <div>
          <label className="block text-sm font-medium text-white mb-1">
            Title <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="e.g., Mission Requirements Document v2.1"
            className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-1">
            Type <span className="text-red-400">*</span>
          </label>
          <select
            value={artifactType}
            onChange={e => setArtifactType(e.target.value)}
            className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
          >
            {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-1">Description</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={4}
            placeholder="Brief description of what this artifact contains and how it relates to the project..."
            className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-white mb-1">Source Date</label>
            <input
              type="date"
              value={sourceDate}
              onChange={e => setSourceDate(e.target.value)}
              className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-white mb-1">Participants</label>
            <input
              type="text"
              value={participantsText}
              onChange={e => setParticipantsText(e.target.value)}
              placeholder="Comma-separated names"
              className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-1">
            Attach File <span className="text-astra-text-dim text-xs">(optional)</span>
          </label>
          <input
            type="file"
            onChange={e => setFile(e.target.files?.[0] || null)}
            accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
            className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white file:mr-3 file:px-3 file:py-1 file:rounded file:border-0 file:bg-blue-600 file:text-white file:cursor-pointer"
          />
          <p className="text-xs text-astra-text-dim mt-1">
            PDF, DOCX, XLSX, TXT, MD, or images up to 50 MB.
          </p>
        </div>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Create Artifact'}
          </button>
          <button
            onClick={() => router.back()}
            className="px-4 py-2 bg-astra-surface-alt hover:bg-astra-border text-white rounded-lg"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 5.5 Detail/edit page — `frontend/src/app/projects/[id]/artifacts/[artifactId]/page.tsx`

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Edit, Save, Trash2, Download, Upload, FileText, X } from 'lucide-react';
import { artifactsApi } from '@/lib/api/artifacts';
import {
  SourceArtifact,
  ArtifactType,
  ARTIFACT_TYPE_LABELS,
  ARTIFACT_TYPE_COLORS,
  Requirement,
  LEVEL_COLORS,
} from '@/lib/types';

export default function ArtifactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const artifactId = Number(params.artifactId);

  const [artifact, setArtifact] = useState<SourceArtifact | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');

  // Edit form state
  const [title, setTitle] = useState('');
  const [artifactType, setArtifactType] = useState('document');
  const [description, setDescription] = useState('');
  const [sourceDate, setSourceDate] = useState('');
  const [participantsText, setParticipantsText] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [a, reqs] = await Promise.all([
        artifactsApi.get(projectId, artifactId),
        artifactsApi.getRequirements(projectId, artifactId),
      ]);
      setArtifact(a);
      setRequirements(reqs);
      setTitle(a.title);
      setArtifactType(a.artifact_type);
      setDescription(a.description || '');
      setSourceDate(a.source_date ? a.source_date.split('T')[0] : '');
      setParticipantsText((a.participants || []).join(', '));
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load artifact');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [projectId, artifactId]);

  const handleSave = async () => {
    setError('');
    try {
      await artifactsApi.update(projectId, artifactId, {
        title,
        artifact_type: artifactType,
        description: description || undefined,
        source_date: sourceDate || undefined,
        participants: participantsText.split(',').map(s => s.trim()).filter(Boolean),
      });
      setEditing(false);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Save failed');
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete artifact "${artifact?.artifact_id}"? This cannot be undone.`)) return;
    try {
      await artifactsApi.delete(projectId, artifactId);
      router.push(`/projects/${projectId}/artifacts`);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Delete failed');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await artifactsApi.uploadFile(projectId, artifactId, file);
      load();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Upload failed');
    }
  };

  const handleDownload = async () => {
    try {
      const blob = await artifactsApi.downloadFile(projectId, artifactId);
      const url = window.URL.createObjectURL(blob as Blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact?.file_path?.split(/[/\\]/).pop() || 'download';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      setError('Download failed');
    }
  };

  if (loading) return <div className="p-6 text-astra-text-dim">Loading…</div>;
  if (!artifact) return <div className="p-6 text-red-400">{error || 'Artifact not found'}</div>;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <button
        onClick={() => router.push(`/projects/${projectId}/artifacts`)}
        className="flex items-center gap-2 text-astra-text-dim hover:text-white mb-4 text-sm"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Source Artifacts
      </button>

      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-mono text-astra-text-dim">{artifact.artifact_id}</span>
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: `${ARTIFACT_TYPE_COLORS[artifact.artifact_type as ArtifactType]}20`,
                color: ARTIFACT_TYPE_COLORS[artifact.artifact_type as ArtifactType],
              }}
            >
              {ARTIFACT_TYPE_LABELS[artifact.artifact_type as ArtifactType]}
            </span>
          </div>
          <h1 className="text-2xl font-semibold text-white">{artifact.title}</h1>
        </div>
        <div className="flex gap-2">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-2 px-3 py-1.5 bg-astra-surface-alt hover:bg-astra-border text-white rounded-lg text-sm"
            >
              <Edit className="w-4 h-4" /> Edit
            </button>
          )}
          <button
            onClick={handleDelete}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg text-sm"
          >
            <Trash2 className="w-4 h-4" /> Delete
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 mb-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        {/* Main content */}
        <div className="col-span-2 space-y-4">
          <div className="bg-astra-surface border border-astra-border rounded-xl p-6">
            {editing ? (
              <div className="space-y-4">
                <input
                  type="text"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
                />
                <select
                  value={artifactType}
                  onChange={e => setArtifactType(e.target.value)}
                  className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
                >
                  {Object.entries(ARTIFACT_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={5}
                  className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
                />
                <div className="grid grid-cols-2 gap-4">
                  <input
                    type="date"
                    value={sourceDate}
                    onChange={e => setSourceDate(e.target.value)}
                    className="px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
                  />
                  <input
                    type="text"
                    value={participantsText}
                    onChange={e => setParticipantsText(e.target.value)}
                    placeholder="Participants (comma-separated)"
                    className="px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleSave}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
                  >
                    <Save className="w-4 h-4" /> Save
                  </button>
                  <button
                    onClick={() => { setEditing(false); load(); }}
                    className="flex items-center gap-2 px-4 py-2 bg-astra-surface-alt hover:bg-astra-border text-white rounded-lg"
                  >
                    <X className="w-4 h-4" /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <h3 className="text-sm font-medium text-astra-text-dim mb-2">Description</h3>
                <p className="text-white whitespace-pre-wrap">
                  {artifact.description || <span className="text-astra-text-dim italic">No description</span>}
                </p>
                {artifact.participants && artifact.participants.length > 0 && (
                  <>
                    <h3 className="text-sm font-medium text-astra-text-dim mt-4 mb-2">Participants</h3>
                    <div className="flex flex-wrap gap-2">
                      {artifact.participants.map((p, i) => (
                        <span key={i} className="px-2 py-1 bg-astra-surface-alt rounded text-sm text-white">{p}</span>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
          </div>

          {/* Linked requirements */}
          <div className="bg-astra-surface border border-astra-border rounded-xl p-6">
            <h3 className="text-white font-medium mb-3">
              Requirements traced to this artifact ({requirements.length})
            </h3>
            {requirements.length === 0 ? (
              <p className="text-sm text-astra-text-dim italic">No requirements link to this artifact yet.</p>
            ) : (
              <div className="space-y-2">
                {requirements.map(r => (
                  <div
                    key={r.id}
                    onClick={() => router.push(`/projects/${projectId}/requirements/${r.id}`)}
                    className="flex items-center gap-3 p-2 hover:bg-astra-surface-alt rounded cursor-pointer"
                  >
                    <span
                      className="w-8 text-xs font-bold text-center px-2 py-0.5 rounded"
                      style={{
                        backgroundColor: `${LEVEL_COLORS[r.level]}20`,
                        color: LEVEL_COLORS[r.level],
                      }}
                    >
                      {r.level}
                    </span>
                    <span className="font-mono text-sm text-astra-text-dim">{r.req_id}</span>
                    <span className="text-white text-sm flex-1 truncate">{r.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* File attachment */}
          <div className="bg-astra-surface border border-astra-border rounded-xl p-4">
            <h3 className="text-sm font-medium text-white mb-3">Attached File</h3>
            {artifact.file_path ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="w-5 h-5 text-blue-400 flex-shrink-0" />
                  <span className="text-sm text-white truncate">
                    {artifact.file_path.split(/[/\\]/).pop()}
                  </span>
                </div>
                <button
                  onClick={handleDownload}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
                >
                  <Download className="w-4 h-4" /> Download
                </button>
                <label className="block mt-2">
                  <span className="block text-xs text-astra-text-dim mb-1">Replace file:</span>
                  <input
                    type="file"
                    onChange={handleFileUpload}
                    accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
                    className="text-xs text-white file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:bg-astra-surface-alt file:text-white file:cursor-pointer"
                  />
                </label>
              </div>
            ) : (
              <label className="block">
                <div className="flex items-center justify-center gap-2 px-3 py-3 border-2 border-dashed border-astra-border rounded text-sm text-astra-text-dim hover:border-blue-500 hover:text-blue-400 cursor-pointer">
                  <Upload className="w-4 h-4" /> Upload file
                </div>
                <input
                  type="file"
                  onChange={handleFileUpload}
                  accept=".pdf,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg"
                  className="hidden"
                />
              </label>
            )}
          </div>

          {/* Metadata */}
          <div className="bg-astra-surface border border-astra-border rounded-xl p-4 space-y-2 text-sm">
            <div>
              <span className="text-astra-text-dim">Source date:</span>{' '}
              <span className="text-white">
                {artifact.source_date ? new Date(artifact.source_date).toLocaleDateString() : '—'}
              </span>
            </div>
            <div>
              <span className="text-astra-text-dim">Created:</span>{' '}
              <span className="text-white">{new Date(artifact.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

### 5.6 Sidebar — add the entry

In `frontend/src/components/layout/Sidebar.tsx` (path may differ — find the actual sidebar component during discovery), find the **ENGINEERING** group and add a Source Artifacts entry between Requirements and Traceability:

```tsx
// In the ENGINEERING group, between Requirements and Traceability:
{
  label: 'Source Artifacts',
  href: `/projects/${projectId}/artifacts`,
  icon: FileText,  // from lucide-react
}
```

(If the sidebar uses a different data structure, adapt accordingly. The intent: visible link to `/projects/[id]/artifacts` from inside any project.)

### 5.7 Wire the L0 requirement form's artifact picker to the API

Find the requirement create/edit form (likely `frontend/src/app/projects/[id]/requirements/new/page.tsx` and the edit page). When `level === 'L0'`, the form should:

1. Fetch the project's source artifacts via `artifactsApi.list(projectId)`
2. Render a `<select>` with options (artifact_id — title)
3. On change, set `source_artifact_id` in the form state
4. Show an inline link "+ Create new artifact" that opens the create page in a new tab
5. Disable save if `level === 'L0'` and `source_artifact_id` is unset, with the existing helpful message

**Replace the existing artifact picker block** (Claude Code: search for `source_artifact_id` in the requirements form) with:

```tsx
import { artifactsApi } from '@/lib/api/artifacts';
import { SourceArtifact } from '@/lib/types';

// inside the component:
const [artifacts, setArtifacts] = useState<SourceArtifact[]>([]);

useEffect(() => {
  if (level === 'L0') {
    artifactsApi.list(projectId).then(setArtifacts).catch(() => setArtifacts([]));
  }
}, [level, projectId]);

// In the JSX, only when level === 'L0':
{level === 'L0' && (
  <div>
    <label className="block text-sm font-medium text-white mb-1">
      Source Artifact <span className="text-red-400">*</span>
    </label>
    {artifacts.length === 0 ? (
      <div className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-sm">
        <span className="text-yellow-400">No source artifacts in this project yet.</span>{' '}
        <a
          href={`/projects/${projectId}/artifacts/new`}
          target="_blank"
          rel="noopener"
          className="text-blue-400 underline"
        >
          Create one →
        </a>
      </div>
    ) : (
      <>
        <select
          value={sourceArtifactId || ''}
          onChange={e => setSourceArtifactId(Number(e.target.value) || undefined)}
          className="w-full px-3 py-2 bg-astra-surface-alt border border-astra-border rounded-lg text-white"
          required
        >
          <option value="">— Select source artifact —</option>
          {artifacts.map(a => (
            <option key={a.id} value={a.id}>
              {a.artifact_id} — {a.title}
            </option>
          ))}
        </select>
        <p className="text-xs text-astra-text-dim mt-1">
          L0 requirements must trace back to a contract, MRD, SOW, or similar artifact.{' '}
          <a
            href={`/projects/${projectId}/artifacts/new`}
            target="_blank"
            rel="noopener"
            className="text-blue-400 hover:underline"
          >
            + Create new artifact
          </a>
        </p>
      </>
    )}
  </div>
)}
```

---

## 6. Smoke tests

After deployment, run all of these. Replace `$TOKEN` with a valid mason JWT.

```bash
# Test 1: Create artifact via API
curl.exe -X POST http://localhost:8000/api/v1/projects/1/artifacts/ ^
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" ^
  -d "{\"title\":\"Test MRD\",\"artifact_type\":\"document\",\"description\":\"Test artifact\"}"
# Expected: 201, returns artifact with auto-generated ART-{code}-001 ID

# Test 2: List artifacts
curl.exe http://localhost:8000/api/v1/projects/1/artifacts/ -H "Authorization: Bearer $TOKEN"
# Expected: array with the test artifact

# Test 3: Stats endpoint
curl.exe http://localhost:8000/api/v1/projects/1/artifacts/stats -H "Authorization: Bearer $TOKEN"
# Expected: array with l0_requirement_count and total_requirement_count fields

# Test 4: Update
curl.exe -X PATCH http://localhost:8000/api/v1/projects/1/artifacts/1 ^
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" ^
  -d "{\"description\":\"Updated description\"}"
# Expected: 200, updated artifact

# Test 5: Delete (no linked reqs) → succeeds
curl.exe -X DELETE http://localhost:8000/api/v1/projects/1/artifacts/1 -H "Authorization: Bearer $TOKEN"
# Expected: 204

# Test 6: Create artifact, then create L0 req referencing it, then try to delete → fails
# (Use the artifact id from a re-create, then create an L0 with source_artifact_id, then DELETE)
# Expected on DELETE: 400 "Cannot delete artifact ... N requirement(s) still reference it"

# Test 7: Frontend visual smoke tests
# - Sidebar: ENGINEERING > Source Artifacts visible inside any project
# - Click "+ New Artifact" from list page → form loads
# - Create artifact, verify it appears in list
# - Click artifact in list → detail page loads with metadata + linked-reqs section
# - Edit button toggles edit mode; Save persists
# - Upload a small PDF, refresh, confirm download button works
# - Open requirement create form, set Level=L0, confirm picker shows the artifact
# - Try to save L0 without picking an artifact → save button disabled or rejects with message
```

---

## 7. Deployment

```bash
git checkout -b feat/source-artifacts-module
# ... apply all changes ...
git add .
git commit -m "feat(artifacts): full Source Artifacts module (TDD-ARTIFACTS-001)"
git push -u origin feat/source-artifacts-module

# Open PR via GitHub link, merge to main

# On the deploy target (PROD PC or this dev box):
git checkout main
git pull
docker compose up -d --build
```

No DB migration required — `SourceArtifact` model is unchanged. Backend restart picks up new endpoints; frontend rebuild picks up new pages.

---

## 8. Rollback

```bash
git revert <merge-commit>
docker compose up -d --build
```

No data destruction. Existing source artifacts remain in the DB; they just become inaccessible via UI until the revert is itself reverted.

---

## 9. Future work (not in scope here)

- **Bulk artifact import** — drop a folder of PDFs onto the list page, auto-create one artifact per file with extracted title from PDF metadata
- **AI-assisted SHALL extraction** — given a PDF artifact, AI extracts contractual SHALL statements and proposes them as L0 reqs
- **Version tracking** — multiple versions of the same artifact (e.g., MRD v1 → v2) with a chain
- **Cross-project artifacts** — single MRD shared across multiple projects in a program
- **Artifact-to-artifact relationships** — "SAR derived from MRD" links

---

## 10. Definition of done

- [ ] Discovery commands run and findings reported
- [ ] All backend endpoints respond per spec (verified by smoke tests 1–6)
- [ ] All frontend pages load without TypeScript errors
- [ ] Sidebar entry visible in ENGINEERING group inside any project
- [ ] L0 requirement form picker populated from API
- [ ] L0 save without artifact rejected at frontend AND backend
- [ ] File upload + download round-trip works
- [ ] Delete-with-references properly blocked
- [ ] Audit events recorded for create/update/delete (verify in `audit_log` table)
- [ ] Branch `feat/source-artifacts-module` pushed, PR opened
