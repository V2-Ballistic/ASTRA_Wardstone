# ASTRA-TDD-LEVELS-001 — Add L0 (Customer/Contractual) Requirement Level

**Version:** 1.0
**Status:** Specification — ready for Claude Code execution
**Owner:** Mason (Systems Engineering)
**Branch:** `feat/l0-customer-requirements` (create from `main`)

---

## 1. Purpose

Extend ASTRA's requirement hierarchy from `L1–L5` to `L0–L5` to capture **customer-imposed** / **contractual** / **defense-sponsored** requirements (MRD, SOW, contract clauses) at a level *above* the system requirements (L1).

L0 is the contractual ceiling. Every L1 should ultimately decompose from at least one L0 to demonstrate complete contract coverage in audits.

## 2. Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Position in hierarchy | L0 sits **above** L1 | Customer reqs are the contractual ceiling that L1 system reqs decompose from |
| Source artifact link | **Required** at save | Forces traceability back to MRD/SOW/contract for audit |
| Edit permissions | **Admin-only** after creation | Customer reqs should not be modified by individual contributors; PMs request changes through change-control |
| Decomposition | L0 → L1 via existing `parent_id` / `decomposition` trace links | No new relationship type needed |
| Quality scoring | Same NASA Appendix C check, but allow lower scores | Customer language often violates SHALL patterns |
| Color | `#DC2626` (deeper red than L1) | Visually signals "above" in the force graph |
| Postgres enum order | `L0` inserted `BEFORE 'L1'` | Preserves natural sort ordering for level-based queries |

## 3. Scope of change

| Layer | File | Change type |
|---|---|---|
| Backend | `backend/app/models/__init__.py` | Add `L0` to `RequirementLevel` enum |
| Backend | `backend/app/services/ai/requirement_writer.py` | Update `_VALID_LEVELS`, `_LEVEL_NEXT`, `_LEVEL_LABELS`; add L0→L1 decompose case |
| Backend | `backend/app/services/level_validator.py` | **New file** — L0 validation helpers |
| Backend | `backend/app/routers/requirements.py` | Wire L0 validators into create/update/delete endpoints |
| Backend | `backend/app/schemas.py` | Add `source_artifact_id` to `RequirementCreate` if missing |
| Database | `database/migrations/0008_add_l0_level.sql` | **New file** — ALTER TYPE requirementlevel |
| Frontend | `frontend/src/lib/types.ts` | Add `L0` to type, labels, colors |
| Frontend | `frontend/src/components/traceability/ForceGraph.tsx` | Add `L0` to local LEVEL_COLORS/LEVEL_LABELS, update Y-axis layout |
| Frontend | Requirement create/edit form | Verify L0 picker and source-artifact enforcement (likely auto-picks up via dropdown iteration) |

---

## 4. Implementation

### 4.1 Backend — Python enum (`backend/app/models/__init__.py`)

**Find:**
```python
class RequirementLevel(str, enum.Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"
```

**Replace with:**
```python
class RequirementLevel(str, enum.Enum):
    L0 = "L0"   # Customer / Contractual (MRD, SOW, contract)
    L1 = "L1"   # System
    L2 = "L2"   # Subsystem
    L3 = "L3"   # Component
    L4 = "L4"   # Sub-component
    L5 = "L5"   # Detail
```

### 4.2 Database migration — `database/migrations/0008_add_l0_level.sql`

**New file — full content:**
```sql
-- ══════════════════════════════════════════════════════════════
--  ASTRA — Migration 0008 — Add L0 Customer/Contractual Level
--  File: database/migrations/0008_add_l0_level.sql
--
--  Adds 'L0' value to the requirementlevel PostgreSQL enum,
--  inserted BEFORE 'L1' to preserve sort ordering.
--
--  Idempotent: safe to re-run.
-- ══════════════════════════════════════════════════════════════

-- Postgres 12+ allows ALTER TYPE ... ADD VALUE outside transactions.
-- Use IF NOT EXISTS for idempotency.

ALTER TYPE requirementlevel ADD VALUE IF NOT EXISTS 'L0' BEFORE 'L1';

-- Verification query (run manually after migration):
-- SELECT unnest(enum_range(NULL::requirementlevel)) AS level;
-- Expected output: L0, L1, L2, L3, L4, L5
```

**Apply with:**
```bash
docker compose exec db psql -U astra -d astra -f /docker-entrypoint-initdb.d/0008_add_l0_level.sql
```

Or directly:
```bash
docker compose exec db psql -U astra -d astra -c "ALTER TYPE requirementlevel ADD VALUE IF NOT EXISTS 'L0' BEFORE 'L1';"
```

### 4.3 Backend — Level validator (`backend/app/services/level_validator.py`)

**New file — full content:**
```python
"""
ASTRA — L0 Level Validation Helpers
=====================================
File: backend/app/services/level_validator.py

Enforces business rules specific to L0 (Customer/Contractual) requirements:
  1. L0 reqs MUST link to a source artifact (MRD, SOW, contract clause).
  2. L0 reqs are edit-restricted to users with role='admin' after creation.

Called from the requirements router on create/update/delete.

NIST 800-53: AC-3 (Access Enforcement), AU-2 (Audit Events for L0 changes)
"""

from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Requirement, User, SourceArtifact


def validate_l0_source_artifact(
    db: Session,
    level: str,
    source_artifact_id: Optional[int],
) -> None:
    """
    Reject creation/update of an L0 requirement that has no linked source artifact.

    Raises:
        HTTPException 400 if level=='L0' and source_artifact_id is missing or invalid.
    """
    if level != "L0":
        return  # Only L0 is gated

    if source_artifact_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "L0 (Customer/Contractual) requirements must link to a source "
                "artifact (e.g. MRD, SOW, contract clause). "
                "Provide 'source_artifact_id' referencing the originating document."
            ),
        )

    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == source_artifact_id
    ).first()
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Source artifact id={source_artifact_id} not found.",
        )


def enforce_l0_admin_only(
    requirement: Requirement,
    current_user: User,
    operation: str = "modify",
) -> None:
    """
    Block non-admin users from editing or deleting an existing L0 requirement.

    Admins always pass. All other roles (PM, requirements_engineer, reviewer,
    stakeholder, developer) are blocked.

    Raises:
        HTTPException 403 if requirement.level == 'L0' and user is not admin.
    """
    # Coerce enum to string for both ORM enum and string columns
    level_value = (
        requirement.level.value
        if hasattr(requirement.level, "value")
        else str(requirement.level)
    )

    if level_value != "L0":
        return  # Only L0 is gated

    role_value = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )

    if role_value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"L0 (Customer/Contractual) requirements are admin-only. "
                f"Cannot {operation} requirement '{requirement.req_id}' as role '{role_value}'. "
                f"Submit a change request to an admin."
            ),
        )
```

### 4.4 Backend — Wire validators into router (`backend/app/routers/requirements.py`)

**Claude Code instructions:**

1. Add imports at the top of the file:
```python
from app.services.level_validator import (
    validate_l0_source_artifact,
    enforce_l0_admin_only,
)
```

2. In the **create requirement** endpoint (typically `POST /requirements/`), after schema validation but before constructing the ORM object, add:
```python
validate_l0_source_artifact(
    db=db,
    level=data.level,
    source_artifact_id=getattr(data, "source_artifact_id", None),
)
```

3. In the **update requirement** endpoint (typically `PATCH /requirements/{id}`), after fetching the existing requirement and before applying changes, add:
```python
# Block non-admin edits of existing L0 reqs
enforce_l0_admin_only(existing, current_user, operation="modify")

# If the update changes level → L0, require a source artifact link
new_level = data.level if data.level is not None else existing.level
new_artifact_id = (
    data.source_artifact_id
    if hasattr(data, "source_artifact_id") and data.source_artifact_id is not None
    else getattr(existing, "source_artifact_id", None)
)
validate_l0_source_artifact(db, new_level, new_artifact_id)
```

4. In the **delete requirement** endpoint, after fetching the existing requirement, add:
```python
enforce_l0_admin_only(existing, current_user, operation="delete")
```

### 4.5 Backend — AI requirement writer (`backend/app/services/ai/requirement_writer.py`)

**Find:**
```python
_LEVEL_NEXT = {"L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5", "L5": "L5"}
_LEVEL_LABELS = {
    "L1": "System", "L2": "Subsystem", "L3": "Component",
    "L4": "Sub-component", "L5": "Detail",
}
```

**Replace with:**
```python
_LEVEL_NEXT = {
    "L0": "L1", "L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5", "L5": "L5",
}
_LEVEL_LABELS = {
    "L0": "Customer/Contractual",
    "L1": "System",
    "L2": "Subsystem",
    "L3": "Component",
    "L4": "Sub-component",
    "L5": "Detail",
}
```

**Find:**
```python
_VALID_LEVELS = {"L1", "L2", "L3", "L4", "L5"}
```

**Replace with:**
```python
_VALID_LEVELS = {"L0", "L1", "L2", "L3", "L4", "L5"}
```

### 4.6 Frontend — Types (`frontend/src/lib/types.ts`)

**Find:**
```typescript
export type RequirementLevel = 'L1' | 'L2' | 'L3' | 'L4' | 'L5';
```

**Replace with:**
```typescript
export type RequirementLevel = 'L0' | 'L1' | 'L2' | 'L3' | 'L4' | 'L5';
```

**Find:**
```typescript
export const LEVEL_LABELS: Record<RequirementLevel, string> = {
  L1: 'L1 — System',
  L2: 'L2 — Subsystem',
  L3: 'L3 — Component',
  L4: 'L4 — Sub-component',
  L5: 'L5 — Detail',
};
```

**Replace with:**
```typescript
export const LEVEL_LABELS: Record<RequirementLevel, string> = {
  L0: 'L0 — Customer / Contractual',
  L1: 'L1 — System',
  L2: 'L2 — Subsystem',
  L3: 'L3 — Component',
  L4: 'L4 — Sub-component',
  L5: 'L5 — Detail',
};
```

**Find:**
```typescript
export const LEVEL_COLORS: Record<RequirementLevel, string> = {
  L1: '#EF4444',
  L2: '#F59E0B',
  L3: '#3B82F6',
  L4: '#8B5CF6',
  L5: '#6B7280',
};
```

**Replace with:**
```typescript
export const LEVEL_COLORS: Record<RequirementLevel, string> = {
  L0: '#DC2626',
  L1: '#EF4444',
  L2: '#F59E0B',
  L3: '#3B82F6',
  L4: '#8B5CF6',
  L5: '#6B7280',
};
```

### 4.7 Frontend — Force graph (`frontend/src/components/traceability/ForceGraph.tsx`)

**Find:**
```typescript
const LEVEL_COLORS: Record<string, string> = {
  L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280',
};

const LEVEL_LABELS: Record<string, string> = {
  L1: 'System', L2: 'Subsystem', L3: 'Component', L4: 'Sub-component', L5: 'Detail',
};
```

**Replace with:**
```typescript
const LEVEL_COLORS: Record<string, string> = {
  L0: '#DC2626', L1: '#EF4444', L2: '#F59E0B', L3: '#3B82F6', L4: '#8B5CF6', L5: '#6B7280',
};

const LEVEL_LABELS: Record<string, string> = {
  L0: 'Customer', L1: 'System', L2: 'Subsystem', L3: 'Component', L4: 'Sub-component', L5: 'Detail',
};
```

**Then locate the Y-axis layout function** (likely a `getLevelY()` or similar that maps level strings to Y-coordinates). The existing pattern probably looks like:
```typescript
const LEVEL_Y: Record<string, number> = {
  L1: 80, L2: 200, L3: 320, L4: 440, L5: 560,
};
```

**If found, replace with:**
```typescript
const LEVEL_Y: Record<string, number> = {
  L0: 40, L1: 130, L2: 230, L3: 330, L4: 430, L5: 530,
};
```

If the layout instead computes Y from `parseInt(level.slice(1))`, add a special case for L0 returning a Y above L1.

### 4.8 Verify the requirement create/edit form

The Requirement create form likely renders the level dropdown by iterating `Object.keys(LEVEL_LABELS)`. If so, L0 picks up automatically — no change needed.

**Claude Code: search the frontend for hardcoded level lists** with:
```bash
grep -rn "'L1'.*'L2'.*'L3'.*'L4'.*'L5'" frontend/src/
grep -rn '"L1".*"L2".*"L3".*"L4".*"L5"' frontend/src/
grep -rn "\\['L1', 'L2', 'L3', 'L4', 'L5'\\]" frontend/src/
```

For any hits outside `types.ts` and `ForceGraph.tsx`, add `L0` to the array (typically as the first element).

### 4.9 Verify the auto-grow / auto-requirements engine

```bash
grep -rn '"level": "L' backend/app/services/interface/
grep -rn "level=\"L" backend/app/services/interface/
```

L0 is exclusively for human-authored customer reqs. **None of the auto-generated reqs should ever land at L0.** If the grep shows level assignments at L0 in the auto engines, that's a bug — replace with L1 or higher.

---

## 5. Deployment

After all file changes are applied:

```bash
# 1. Apply DB migration (live, no downtime — ADD VALUE is non-blocking in PG 16)
docker compose exec db psql -U astra -d astra -c "ALTER TYPE requirementlevel ADD VALUE IF NOT EXISTS 'L0' BEFORE 'L1';"

# 2. Verify enum
docker compose exec db psql -U astra -d astra -c "SELECT unnest(enum_range(NULL::requirementlevel));"
# Expected: L0, L1, L2, L3, L4, L5

# 3. Restart backend (picks up Python enum and validator)
docker compose restart backend

# 4. Rebuild frontend (NEXT_PUBLIC_API_URL is baked at build time)
docker compose up -d --build frontend
```

---

## 6. Smoke tests

Run these after deployment to confirm the change is wired correctly. Replace `$TOKEN` with a valid mason JWT (from `POST /api/v1/auth/login`).

```bash
# Test 1: Create an L0 WITHOUT source artifact → should fail 400
curl.exe -X POST http://localhost:8000/api/v1/requirements/ ^
  -H "Authorization: Bearer $TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Test L0\",\"statement\":\"The system shall meet contract X.\",\"req_type\":\"functional\",\"priority\":\"high\",\"level\":\"L0\",\"project_id\":1}"
# Expected: HTTP 400, "L0 ... must link to a source artifact"

# Test 2: Create a source artifact, then create L0 WITH it → should succeed
curl.exe -X POST http://localhost:8000/api/v1/artifacts/ ^
  -H "Authorization: Bearer $TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"artifact_id\":\"SA-MRD-001\",\"title\":\"MRD\",\"artifact_type\":\"document\",\"description\":\"Mission Requirements Document\",\"project_id\":1}"
# Note returned id (e.g. 1)

curl.exe -X POST http://localhost:8000/api/v1/requirements/ ^
  -H "Authorization: Bearer $TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Test L0\",\"statement\":\"The system shall meet contract X.\",\"req_type\":\"functional\",\"priority\":\"high\",\"level\":\"L0\",\"project_id\":1,\"source_artifact_id\":1}"
# Expected: HTTP 201, requirement created

# Test 3: Login as a non-admin user, try to edit the L0 → should fail 403
# (Login as 'sebastian' or any non-admin, get token, then:)
curl.exe -X PATCH http://localhost:8000/api/v1/requirements/{REQ_ID} ^
  -H "Authorization: Bearer $NONADMIN_TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"Modified\"}"
# Expected: HTTP 403, "L0 ... admin-only"

# Test 4: Frontend visual — open a requirement page, confirm L0 appears in the
# level dropdown, and the force graph places L0 nodes above L1.
```

---

## 7. Rollback

If anything goes wrong:

```bash
# Postgres does NOT support removing an enum value cleanly without recreating the type.
# Instead, leave 'L0' in the enum (it's harmless if unused) and revert code only:

git revert <commit-sha>
docker compose restart backend
docker compose up -d --build frontend
```

If you've already created L0 requirements that need to be removed before reverting:
```sql
UPDATE requirements SET level = 'L1' WHERE level = 'L0';
DELETE FROM requirements WHERE level = 'L0';  -- alternative
```

---

## 8. Audit & change-management notes

- L0 changes (create, update, delete) are already captured by the existing `audit_log` hash chain via `record_event()` calls in the requirements router. No additional audit instrumentation needed.
- For the SHALL-quality scoring exception (allowing lower scores at L0), no code change required — the quality checker runs and flags issues, but L0 reqs aren't blocked from save based on score.

---

## 9. Future work (out of scope for this TDD)

- **L0 baseline lock** — once an L0 is part of a baseline, even admins must use a formal change request workflow to modify it. Track in ASTRA-TDD-LEVELS-002.
- **Contract decomposition coverage report** — query: "Show me all L0s that have zero L1 children" — useful for identifying contract requirements not yet decomposed.
- **L0 import from MRD/SOW PDFs** — AI extraction of contractual SHALL statements with auto-link to the source PDF.

---

## 10. Definition of done

- [ ] All file changes applied
- [ ] DB migration applied; `enum_range(NULL::requirementlevel)` returns L0–L5
- [ ] Backend container restarts cleanly with no startup errors
- [ ] Frontend rebuilds with no TypeScript errors
- [ ] All four smoke tests pass
- [ ] Commit on `feat/l0-customer-requirements` branch, PR opened to `main`
