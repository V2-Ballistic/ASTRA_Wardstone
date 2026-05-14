# Claude Code Execution Prompt — Catalog STEP Support (additive)

> Adds CAD/STEP file ingestion to the **existing** ASTRA catalog system. This prompt is scoped to additive changes only. The existing `Supplier` / `SupplierDocument` / `CatalogPart` / `CatalogConnector` / `CatalogPin` / `PendingCatalogImport` tables and their `/api/v1/catalog/*` router stay intact and unchanged in shape — we only ADD columns, ADD enum values, and ADD endpoints.

> **Critical context:** A prior session attempted a full catalog "unification" that conflicted with the existing schema. That work was reverted; salvageable pieces (the STEP parser code and seed JSON) live at `C:\Users\WardStone\Documents\astra-salvage\`. The current head is migration `0028` (`0028_add_l0_level.py`).

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`** (PowerShell, Docker Desktop). Add STEP file ingestion to the catalog so users can drop a `.STEP` file in, have the parser auto-detect manufacturer / MPN / material / bounding box / part subtype, auto-create the supplier if it's not on the list, and land everything in the existing `pending_catalog_imports` review queue.

Validation case is a McMaster-Carr file at `C:\Users\WardStone\Documents\astra-salvage\92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP` (or wherever the user places it; the prompt assumes it's placed at `backend/tests/fixtures/cad/` before Phase 3 tests run).

Commit the work in four phases. Use commit messages of form `phase-<n>(catalog-step): <summary>`.

---

## Pre-flight — read these files first, in order, BEFORE writing anything

1. **`backend/app/models/catalog.py`** — the existing catalog ORM. You're extending `Supplier` and `CatalogPart`, adding a new `SupplierAlias` model. The existing `PartClass`, `LRUClass`, `LifecycleStatus`, `ConnectorGender`, `SignalType`, `SignalDirection`, `SupplierDocumentType`, `ExtractionStatus`, `PendingImportStatus` enums all stay; we ADD values to `PartClass` only.

2. **`backend/app/routers/catalog.py`** — the existing catalog router. Read it end-to-end. You're appending a new endpoint `POST /catalog/upload-step` and reusing the existing `_audit`, `_user_role`, `_require_req_eng_plus`, `SUPPLIER_DOC_DIR` helpers and the existing `Supplier`/`SupplierDocument`/`PendingCatalogImport` patterns. Don't refactor anything that's already there.

3. **`backend/app/schemas/catalog.py`** — extend with new fields on `CatalogPartCreate`/`Update`/`Response`/`Summary`, plus new `SupplierAliasResponse`, plus a new `StepUploadResponse` for the upload endpoint.

4. **`backend/alembic/versions/0028_add_l0_level.py`** — the **head**. Read it for the `op.get_context().autocommit_block()` pattern that you MUST use for `ALTER TYPE ... ADD VALUE` (PostgreSQL forbids those inside a transaction). New migration chains as `down_revision = "0028"`.

5. **`frontend/src/app/catalog/page.tsx`** — the existing Catalog landing page with three tabs (Suppliers / Parts / Pending Imports). You're adding an "Upload STEP" button to the Parts tab toolbar (alongside the existing "New Part" button) and adding a basic detail page at `/catalog/pending-imports/[id]/page.tsx` that supports approve/reject for both ICD-derived AND STEP-derived imports.

6. **`frontend/src/lib/catalog-api.ts`** and **`frontend/src/lib/catalog-types.ts`** — extend with new fields, new PartClass values, and a `uploadStep` helper.

7. **Salvage directory** at `C:\Users\WardStone\Documents\astra-salvage\` — contains a previous attempt's `cad/step_parser.py` and `catalog_seed/*.json` files. **Use them as a starting point for parser logic and seed data; rewrite them to match the actual `CatalogPart` schema (which uses `part_number` not `wpn`, `mass_kg` not `mass_g`, etc.).** Don't blindly copy. Read first, then rewrite to fit.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | Extend the existing `PartClass` enum with mechanical values rather than introducing a parallel `part_kind` enum. | Less ceremony; the existing enum is already a flat list. |
| AD-2 | Add CAD columns directly to `catalog_parts` rather than a child `catalog_part_cad` table. | Existing table already has 50+ columns of similar specs; another join on every read isn't worth it. |
| AD-3 | New endpoint `POST /catalog/upload-step` rather than overloading the existing `POST /catalog/suppliers/{id}/documents/upload`. | Different upload semantics: STEP requires no supplier upfront (auto-detect from filename); PDF requires it. Cleaner to keep flows distinct. |
| AD-4 | On STEP upload, auto-create the detected supplier immediately (before approval). | Simplest; satisfies `pending_catalog_imports.supplier_id NOT NULL`. Empty suppliers from rejected imports can be cleaned up admin-side; cost is essentially zero. |
| AD-5 | pythonOCC integration is opportunistic with try/except graceful fallback. **Do NOT modify the Docker image** to install pythonOCC; that's a separate operational task. The pure-Python path provides ~80% of the value. | Image rebuild is non-trivial and out of scope here. |
| AD-6 | Migration uses `ADD COLUMN IF NOT EXISTS` and `ADD VALUE IF NOT EXISTS` patterns so it's safely re-runnable. | Project standing rule, and the existing `0028_add_l0_level.py` does this — copy the pattern. |

---

## Standing rules (subset that matters)

1. **Drop-in file replacements only.** No partial edits, no `# ...existing code...` placeholders. Whole-file output. The existing `catalog.py` model and router are LARGE — when you edit them, deliver the full updated file.
2. **No Alembic autogenerate.** Migration `0029` is hand-written using `op.execute(text("..."))` and `op.get_context().autocommit_block()` for enum value adds. Mirror the style of `0028_add_l0_level.py`.
3. **SQLAlchemy enum extraction:** use `.value` not `str()`. PostgreSQL rejects `"ClassName.VALUE"` form.
4. **API list endpoints cap at `limit=200`.** Larger values return 422.
5. **Backend commands inside the container:** `docker compose exec backend <cmd>`, `docker compose exec db psql -U astra -d astra`. The Windows host doesn't have Node or pytest installed — use `docker compose exec frontend npm <cmd>` and `docker compose exec backend python -m pytest <cmd>`. If pytest missing in image, `pip install pytest pytest-asyncio httpx` into the running container.
6. **PowerShell:** `curl` is an alias — use `curl.exe` for HTTP testing. Avoid `$PID` (reserved).
7. **React hooks before any early `return`.** Optional chaining (`pendingImport?.extracted_data`) for null safety.
8. **TypeScript validates clean** after each frontend change: `docker compose exec frontend npx tsc --noEmit`.
9. **Python AST validation:** every Python file must parse via `python3 -c "import ast; ast.parse(open('<f>').read())"` before delivery.
10. **Login during testing:** `mason` / `password123` (admin, user_id=1).
11. **Don't drop / don't touch:** existing rows in `requirements`, `projects`, `users`, `audit_log`, `electronic_signatures`, `suppliers`, `supplier_documents`, `catalog_parts`, `catalog_connectors`, `catalog_pins`, `pending_catalog_imports`. The 8 existing requirements + 1 project must remain.
12. **Don't refactor existing code outside the scope of this prompt.** The catalog router and ORM are well-structured. Add to them, don't reshape them. The frontend Catalog page works; we're adding a button and a detail page, not rewriting.

---

## Validation fixture — the McMaster screw

Before Phase 3 starts, the user places `92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP` at `backend/tests/fixtures/cad/`. Expected extraction (per the salvage TDD-CAT-001 §6, but mapped to this schema):

| Field | Source in STEP | Lands in `extracted_data` JSONB as | Confidence |
|-------|----------------|-------------------------------------|------------|
| `original_filename` | `FILE_NAME` header | `original_filename` | high |
| `cad_authoring_tool` | `FILE_NAME` arg 6 | `cad_authoring_tool` → `"SolidWorks 2025"` | high |
| `schema` | `FILE_SCHEMA` | `schema` → `"AUTOMOTIVE_DESIGN"` | high |
| `is_assembly` | count of `PRODUCT_RELATED_PRODUCT_CATEGORY` rows | `is_assembly` → `false` | high |
| `manufacturer` | regex `^(\d{5}[A-Z]\d{1,4})_` on filename | `manufacturer` → `"McMaster-Carr"` | high |
| `part_number` (the supplier's MPN) | first capture of vendor regex | `part_number` → `"92196A196"` | high |
| `material_name` | tokenize remainder of filename | `material_name` → `"18-8 Stainless Steel"` | high |
| `material_class` | normalize via material lexicon | `material_class` → `"stainless_steel"` | high |
| `part_class` | derived from part-type lexicon | `part_class` → `"fastener_screw"` (NEW enum value) | high |
| `part_subtype` | finer-grain lexicon | `part_subtype` → `"socket_head_cap_screw"` | high |
| `bbox_x_mm`, `bbox_y_mm`, `bbox_z_mm` | min/max scan of `CARTESIAN_POINT` × unit factor | `bbox_x_mm` etc. | high |
| `native_units` | `LENGTH_MEASURE_WITH_UNIT` value (0.0254 → INCH) | `native_units` → `"inch"` | high |

The `extracted_data` JSONB on `pending_catalog_imports` holds these field-by-field. The single `extraction_confidence` numeric column on the row gets the average or the minimum of the field-level confidences (your call — go with average).

---

## Phase 1 — Migration 0029

**File:** `backend/alembic/versions/0029_catalog_step_support.py`

**Spec:**
- `down_revision = "0028"`
- `revision = "0029"`
- Use `op.get_context().autocommit_block()` for the `ALTER TYPE ADD VALUE` calls — copy the pattern from `0028_add_l0_level.py`.

**Operations (idempotent):**

```python
def upgrade() -> None:
    # 1. is_in_house on suppliers
    op.execute(
        "ALTER TABLE suppliers "
        "ADD COLUMN IF NOT EXISTS is_in_house BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # 2. supplier_aliases table
    op.execute("""
        CREATE TABLE IF NOT EXISTS supplier_aliases (
            id          BIGSERIAL    PRIMARY KEY,
            supplier_id INTEGER      NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            alias       VARCHAR(255) NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_supplier_aliases_supplier ON supplier_aliases(supplier_id)")

    # 3. New mechanical part_class enum values (must be outside transaction)
    with op.get_context().autocommit_block():
        for v in (
            "fastener_screw", "fastener_bolt", "nut", "washer",
            "bracket", "housing", "enclosure", "seal_o_ring",
            "bearing", "spring", "structural_member", "mechanical_other",
        ):
            op.execute(f"ALTER TYPE part_class ADD VALUE IF NOT EXISTS '{v}'")

    # 4. CAD columns on catalog_parts
    for col_sql in [
        "ADD COLUMN IF NOT EXISTS part_subtype          VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS material_name         VARCHAR(128)",
        "ADD COLUMN IF NOT EXISTS material_class        VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS bbox_x_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS bbox_y_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS bbox_z_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS volume_mm3            NUMERIC(14,4)",
        "ADD COLUMN IF NOT EXISTS cad_step_path         TEXT",
        "ADD COLUMN IF NOT EXISTS cad_preview_path      TEXT",
        "ADD COLUMN IF NOT EXISTS cad_authoring_tool    VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS native_units          VARCHAR(16)",
        "ADD COLUMN IF NOT EXISTS deleted_at            TIMESTAMPTZ",
    ]:
        op.execute(f"ALTER TABLE catalog_parts {col_sql}")

    op.execute("CREATE INDEX IF NOT EXISTS ix_catalog_parts_material_class ON catalog_parts(material_class)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_catalog_parts_part_subtype  ON catalog_parts(part_subtype)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_catalog_parts_deleted_at    ON catalog_parts(deleted_at)")

    # 5. Seed Wardstone supplier as in-house (idempotent — ON CONFLICT)
    op.execute("""
        INSERT INTO suppliers (name, short_name, country, is_active, is_in_house, created_by_id, created_at, updated_at)
        SELECT 'Wardstone', 'WS', 'US', TRUE, TRUE, u.id, NOW(), NOW()
        FROM users u
        WHERE u.username = 'mason'
        ON CONFLICT (name) DO UPDATE SET is_in_house = TRUE
    """)
    op.execute("""
        INSERT INTO supplier_aliases (supplier_id, alias)
        SELECT s.id, a.alias
        FROM suppliers s
        CROSS JOIN (VALUES ('Wardstone'), ('WardStone'), ('WARDSTONE'), ('Ward Stone'), ('WS')) AS a(alias)
        WHERE s.name = 'Wardstone'
        ON CONFLICT (alias) DO NOTHING
    """)


def downgrade() -> None:
    # Forward-only on enum values — PG doesn't support clean removal.
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_material_class")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_part_subtype")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_deleted_at")
    for col in ("part_subtype", "material_name", "material_class", "bbox_x_mm", "bbox_y_mm",
                "bbox_z_mm", "volume_mm3", "cad_step_path", "cad_preview_path",
                "cad_authoring_tool", "native_units", "deleted_at"):
        op.execute(f"ALTER TABLE catalog_parts DROP COLUMN IF EXISTS {col}")
    op.execute("DROP INDEX IF EXISTS ix_supplier_aliases_supplier")
    op.execute("DROP TABLE IF EXISTS supplier_aliases CASCADE")
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS is_in_house")
    # Note: PartClass enum values stay (PG can't drop them cleanly).
```

**Verify:**
```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
# → 0029 (head)

docker compose exec db psql -U astra -d astra -c "\d suppliers" | findstr is_in_house
docker compose exec db psql -U astra -d astra -c "\d supplier_aliases"
docker compose exec db psql -U astra -d astra -c "\d catalog_parts" | findstr "material_class bbox cad_step"
docker compose exec db psql -U astra -d astra -c "SELECT name, is_in_house FROM suppliers WHERE is_in_house = TRUE"
# → should return 1 row: Wardstone | t
docker compose exec db psql -U astra -d astra -c "SELECT alias FROM supplier_aliases WHERE supplier_id = (SELECT id FROM suppliers WHERE name='Wardstone')"
# → 5 aliases
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirements"
# → still 8
```

Commit: `phase-1(catalog-step): migration 0029 — CAD fields, mechanical part_class values, Wardstone seed, supplier_aliases`

---

## Phase 2 — Backend models, schemas, parser, seed JSON

### 2.1 Update `backend/app/models/catalog.py`

Drop-in full replacement. Changes:

1. Add new values to the `PartClass` enum (matching the migration):
   ```python
   class PartClass(str, enum.Enum):
       # existing electrical values...
       PROCESSOR        = "processor"
       SENSOR           = "sensor"
       # ... (preserve all existing values) ...

       # NEW mechanical values
       FASTENER_SCREW       = "fastener_screw"
       FASTENER_BOLT        = "fastener_bolt"
       NUT                  = "nut"
       WASHER               = "washer"
       BRACKET              = "bracket"
       HOUSING              = "housing"
       ENCLOSURE            = "enclosure"
       SEAL_O_RING          = "seal_o_ring"
       BEARING              = "bearing"
       SPRING               = "spring"
       STRUCTURAL_MEMBER    = "structural_member"
       MECHANICAL_OTHER     = "mechanical_other"
   ```

2. Add `is_in_house` to `Supplier` model. Add a `aliases` relationship to `SupplierAlias`.

3. Add CAD columns to `CatalogPart` matching the migration. Make all nullable.

4. New model `SupplierAlias`:
   ```python
   class SupplierAlias(Base):
       __tablename__ = "supplier_aliases"

       id          = Column(BigInteger, primary_key=True)
       supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
       alias       = Column(String(255), nullable=False, unique=True)
       created_at  = Column(DateTime(timezone=True), server_default=func.now())

       supplier = relationship("Supplier", back_populates="aliases")
   ```

5. Add `aliases = relationship("SupplierAlias", back_populates="supplier", cascade="all, delete-orphan")` to `Supplier`.

6. Make sure the new model is exported via `app/models/__init__.py`.

### 2.2 Update `backend/app/schemas/catalog.py`

- Extend `CatalogPartCreate`, `CatalogPartUpdate`, `CatalogPartResponse`, `CatalogPartSummary` with the new optional fields (`part_subtype`, `material_name`, `material_class`, `bbox_x_mm`, `bbox_y_mm`, `bbox_z_mm`, `volume_mm3`, `cad_step_path`, `cad_preview_path`, `cad_authoring_tool`, `native_units`).
- Add `is_in_house: bool = False` to `SupplierResponse` and `SupplierCreate`.
- New `SupplierAliasResponse(BaseModel)`: `{id, supplier_id, alias, created_at}`.
- New `StepUploadResponse(BaseModel)`:
  ```python
  class StepUploadResponse(BaseModel):
      pending_import_id: int
      supplier_document_id: int
      detected_supplier_id: int
      detected_supplier_name: str
      supplier_was_created: bool
      extraction_confidence: float
      warnings: list[str]
  ```

### 2.3 Salvage and adapt the STEP parser

Copy from salvage as starting point, then refactor:

```powershell
# Run BEFORE writing parser code
Copy-Item -Recurse C:\Users\WardStone\Documents\astra-salvage\cad backend\app\services\cad
Copy-Item -Recurse C:\Users\WardStone\Documents\astra-salvage\catalog_seed backend\catalog_seed
```

Then **rewrite** the parser to fit the actual `CatalogPart` schema:
- The parser's output dict keys must match `extracted_data` JSONB keys we want stored on `pending_catalog_imports`.
- Manufacturer goes to `manufacturer` (the supplier's name; resolved to supplier_id at upload time).
- MPN goes to `part_number` (matches `catalog_parts.part_number`).
- `material_class` and `material_name` map directly.
- `part_class` value must be one of the new enum string values (e.g. `"fastener_screw"`). The old salvage code may have used different keys (e.g. `"manufacturer_part_number"` → rename to `"part_number"`; `"mass_g"` → mass in kg if extracted from pythonOCC, key it `"mass_kg"`).

The parser entry point:

```python
@dataclass
class ParsedStepResult:
    extracted: dict[str, Any]            # keys match catalog_parts column names
    confidence: dict[str, str]            # per-field: high|medium|low
    detected_supplier_canonical: Optional[str]   # "McMaster-Carr"
    detected_supplier_aliases: list[str]          # ["McMaster", "MCMASTER", ...]
    parser_version: str
    warnings: list[str]

def parse_step_file(file_path: Path, *, run_pythonocc: bool = True) -> ParsedStepResult:
    ...
```

Files to deliver under `backend/app/services/cad/`:
- `__init__.py`
- `step_parser.py` — main entry point, regex-based pure-Python extraction (HEADER, PRODUCT entity, CARTESIAN_POINT bbox, LENGTH_MEASURE_WITH_UNIT detection)
- `supplier_detection.py` — vendor pattern table loader; regex match against filename; alias-aware supplier resolution
- `material_lexicon.py` — load + match material aliases
- `part_type_lexicon.py` — load + match part-type tokens (most-specific-first)

Files to deliver under `backend/catalog_seed/`:
- `vendor_patterns.json` — minimum: McMaster-Carr (`^(\d{5}[A-Z]\d{1,4})_`), Misumi, Grainger, MSC patterns. Each entry: `supplier_canonical`, `filename_regex`, `mpn_capture_group`, `aliases[]`.
- `material_lexicon.json` — `stainless_steel: ["18-8 Stainless Steel", ...]`, `aluminum`, `titanium`, `carbon_steel`, `alloy_steel`, `brass`, `plastic_nylon`, `plastic_acetal`, `plastic_ptfe`. Each with `density_g_per_mm3` for the optional pythonOCC mass calc.
- `part_type_lexicon.json` — list of `{tokens: [...], part_class: "...", part_subtype: "..."}`. Most-specific first ("socket head cap screw" before "screw").

Optional pythonOCC enrichment:
```python
def parse_step_file(file_path, *, run_pythonocc=True):
    result = _parse_pure_python(file_path)
    if run_pythonocc:
        try:
            from OCP.STEPControl import STEPControl_Reader
            from OCP.BRepGProp import BRepGProp
            # ... volume, mass (volume × density), surface_area ...
        except ImportError:
            result.warnings.append("pythonOCC not available — volume/mass/preview skipped")
        except Exception as e:
            result.warnings.append(f"pythonOCC processing failed: {e}")
    return result
```

Don't try to install pythonOCC. If the import fails, fall back gracefully — the pure-Python path works.

### 2.4 Verify Phase 2

```powershell
docker compose exec backend python -c "from app.models.catalog import CatalogPart, SupplierAlias, PartClass; print(PartClass.FASTENER_SCREW.value)"
# → fastener_screw

docker compose exec backend python -c "from app.services.cad.step_parser import parse_step_file; print('ok')"
# → ok
```

Commit: `phase-2(catalog-step): models, schemas, STEP parser, seed JSON`

---

## Phase 3 — STEP upload endpoint

### 3.1 Add to `backend/app/routers/catalog.py`

Extend the existing router (whole-file replacement). Append a new section for the STEP upload endpoint. Reuse the existing `_audit`, `_require_req_eng_plus`, `SUPPLIER_DOC_DIR` helpers.

```python
@router.post("/upload-step", response_model=StepUploadResponse, status_code=201)
async def upload_step_file(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a STEP file. The parser runs inline:
      1. Hash + dedup (by sha256 across ALL suppliers — STEP files are
         globally identifiable by content).
      2. Run STEP parser → extract metadata, detect supplier.
      3. Resolve supplier: alias lookup → name lookup → auto-create.
      4. Save file to SUPPLIER_DOC_DIR.
      5. Create SupplierDocument linked to detected/created supplier.
      6. Create PendingCatalogImport with extracted_data.
      7. Return IDs + detection result.
    """
    _require_req_eng_plus(current_user)
    # ... implementation per spec below ...
```

**Implementation requirements:**

1. **Hash and dedup.** sha256 the file content. Reject (409) if any `SupplierDocument` already has this hash for ANY supplier.

2. **Save file.** Use the existing `SUPPLIER_DOC_DIR` pattern: `{uuid}.step`.

3. **Parse.** Call `parse_step_file(temp_path, run_pythonocc=True)`. If parser raises, return 422 with the error.

4. **Resolve supplier:**
   - If `result.detected_supplier_canonical` is None: link to Wardstone (in-house).
   - Else: look up in `supplier_aliases.alias` (case-insensitive). If hit, use that supplier_id. If miss, also try `Supplier.name` ilike match against the canonical and all detected aliases.
   - If still no match: create a new `Supplier` row with `name=detected_supplier_canonical`, `is_active=TRUE`, `is_in_house=FALSE`. Then insert all `result.detected_supplier_aliases` into `supplier_aliases` linked to the new supplier. Set `supplier_was_created=True` in the response.

5. **Create `SupplierDocument`** with `document_type=SupplierDocumentType.OTHER` (or add a new enum value `STEP_FILE` in the migration if you prefer — your call; OTHER is fine for now), `file_path`, `file_size_bytes`, `sha256`, `mime_type='application/STEP'` or `model/step`, `extraction_status=ExtractionStatus.PENDING_REVIEW` (parser already ran — skip the `EXTRACTING` state), `extraction_log={"warnings": result.warnings, "parser_version": result.parser_version, "confidence_per_field": result.confidence}`, `extraction_at=now`.

6. **Create `PendingCatalogImport`** with `source_document_id`, `supplier_id`, `extracted_data=result.extracted`, `extraction_warnings=result.warnings`, `extraction_confidence=avg(result.confidence numeric values)` (where high=1.0, medium=0.6, low=0.3).

7. **Audit emit:**
   - `catalog.supplier.auto_created` if supplier was created (with `{detected_name, alias_count, document_id}`)
   - `catalog.step_uploaded` for every upload (with `{supplier_id, document_id, pending_import_id, mpn, sha256_short}`)

8. **Return** `StepUploadResponse` per the schema in Phase 2.2.

### 3.2 Tests

Place fixture: user puts the McMaster STEP at `backend/tests/fixtures/cad/92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP` before running tests. If it's not there, the AC-3 test should be marked skip with a clear message — don't fail the suite.

**`backend/tests/test_step_parser.py`:**
- `test_mcmaster_socket_head_screw` — parse the fixture; assert all the AC-3 extractions hit per the validation table above.
- `test_inhouse_no_vendor_pattern` — fabricate a STEP file with a non-vendor filename; assert `detected_supplier_canonical is None`.
- `test_pythonocc_unavailable_fallback` — monkeypatch the OCC import to fail; assert pure-Python fields still populate, warning logged.
- `test_corrupted_step_returns_useful_error` — empty file or junk content; parser raises with a clear message rather than crashing.

**`backend/tests/test_supplier_aliases.py`:**
- `test_alias_resolution_case_insensitive` — seed McMaster + aliases; resolution finds it via "MCMASTER", "mcmaster", "McMaster".
- `test_unique_alias_constraint` — inserting same alias twice raises IntegrityError.
- `test_alias_cascade_on_supplier_delete` — deleting the supplier deletes all aliases.

**`backend/tests/test_step_upload_flow.py`:**
- `test_upload_mcmaster_creates_supplier_first_time` — upload the fixture, assert McMaster-Carr supplier was created with `supplier_was_created=True`, 4+ aliases inserted, 1 SupplierDocument, 1 PendingCatalogImport with extracted_data populated.
- `test_upload_mcmaster_reuses_supplier_second_time` — upload a *different* McMaster STEP (you can synthesize a minimal one with a different MPN in the filename), assert `supplier_was_created=False` and total Supplier rows unchanged.
- `test_upload_inhouse_links_to_wardstone` — synthesize a STEP filename with no vendor pattern; assert it links to Wardstone (which the migration seeded).
- `test_upload_dedup_rejects_duplicate_hash` — upload the same file twice, second call returns 409.
- `test_upload_then_approve_creates_catalog_part` — upload + then call existing `POST /catalog/pending-imports/{id}/approve`; assert a `CatalogPart` is created with correct `part_class=fastener_screw`, `material_class=stainless_steel`, etc.

### 3.3 Verify

```powershell
docker compose exec backend python -m pytest tests/test_step_parser.py tests/test_supplier_aliases.py tests/test_step_upload_flow.py -v
```

If pytest isn't installed:
```powershell
docker compose exec backend pip install pytest pytest-asyncio httpx
```

Commit: `phase-3(catalog-step): /catalog/upload-step endpoint, supplier auto-create, full test coverage`

---

## Phase 4 — Frontend STEP upload + minimal review page

### 4.1 Update `frontend/src/lib/catalog-types.ts`

- Add new `PartClass` values to the type union: `'fastener_screw'`, `'fastener_bolt'`, `'nut'`, `'washer'`, `'bracket'`, `'housing'`, `'enclosure'`, `'seal_o_ring'`, `'bearing'`, `'spring'`, `'structural_member'`, `'mechanical_other'`.
- Add labels to `PART_CLASS_LABELS`.
- Add `is_in_house?: boolean` to `Supplier` type.
- Add new fields to `CatalogPart` type matching the model: `part_subtype`, `material_name`, `material_class`, `bbox_x_mm`, `bbox_y_mm`, `bbox_z_mm`, `volume_mm3`, `cad_step_path`, `cad_preview_path`, `cad_authoring_tool`, `native_units`.
- New type `StepUploadResponse` matching the backend schema.

### 4.2 Update `frontend/src/lib/catalog-api.ts`

Add:

```typescript
async uploadStep(file: File): Promise<AxiosResponse<StepUploadResponse>> {
  const form = new FormData();
  form.append('file', file);
  return apiClient.post('/catalog/upload-step', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
},

async getPendingImport(id: number): Promise<AxiosResponse<PendingCatalogImport>> {
  return apiClient.get(`/catalog/pending-imports/${id}`);
},

async patchPendingImport(id: number, body: Partial<PendingCatalogImport>): Promise<AxiosResponse<PendingCatalogImport>> {
  return apiClient.patch(`/catalog/pending-imports/${id}`, body);
},

async approvePendingImport(id: number): Promise<AxiosResponse<CatalogPart>> {
  return apiClient.post(`/catalog/pending-imports/${id}/approve`);
},

async rejectPendingImport(id: number, reason?: string): Promise<AxiosResponse<PendingCatalogImport>> {
  return apiClient.post(`/catalog/pending-imports/${id}/reject`, { reason });
},
```

### 4.3 Update `frontend/src/app/catalog/page.tsx`

Whole-file drop-in replacement. Changes:

1. **Parts tab toolbar:** add an "Upload STEP" button next to the existing "New Part" button. Use `Upload` icon from lucide-react. Style: same as "New Part" but with a faint emerald accent (`bg-emerald-600 hover:bg-emerald-500`) so users can distinguish.
2. **Hidden file input** triggered by the button. On `<input>` change → call `catalogAPI.uploadStep(file)` → on success, navigate to `/catalog/pending-imports/${response.data.pending_import_id}` (the new review page).
3. **Pending Imports tab:** make rows clickable — clicking row navigates to `/catalog/pending-imports/${row.id}`. Remove the "Phase 7 preview" amber banner copy (Phase 7 has effectively shipped for STEP files now).
4. **Suppliers tab:** add a small "In House" badge in green next to the supplier name when `s.is_in_house === true`.

Don't change the page structure (three tabs, search, filters) or the card-vs-table layout. Just the additions above.

### 4.4 New file: `frontend/src/app/catalog/pending-imports/[id]/page.tsx`

A minimal review page that handles BOTH STEP-derived AND ICD-derived imports (since both use the same `pending_catalog_imports` table). Layout:

- **Top bar:** breadcrumb (Catalog → Pending Imports → #{id}), status pill, "Reject" and "Approve & Create Part" buttons.
- **Detected supplier banner** (if `extraction_warnings` includes a "supplier_was_auto_created" flag, OR if you can detect the auto-create from the audit log — for v1, just show the supplier name with a "Linked to: <name>" label):
  - If supplier `is_in_house` → green banner: "Linked to in-house supplier Wardstone".
  - Else → blue banner: "Linked to supplier <name>".
- **Extracted data form:** render `extracted_data` as a key-value table. Each row has a label, an input, and a confidence pill (green/amber/red) read from `extraction_log.confidence_per_field` (added by the new STEP flow). Edits PATCH back to `/catalog/pending-imports/{id}` with `{extracted_data: {...}}`.
- **Action buttons:**
  - **Approve & Create Part** → POST `/catalog/pending-imports/{id}/approve`. On success, navigate to `/catalog/parts/${response.data.id}`.
  - **Reject** → opens a small modal asking for reason; POST `/catalog/pending-imports/{id}/reject` with reason; navigate back to `/catalog?tab=pending`.
- **Below the form:**
  - "Source document" section showing filename, file size, sha256 short, mime type, and a download link to `/catalog/documents/{source_doc_id}/file`.
  - "Extraction warnings" expandable section showing `extraction_warnings` JSONB content.

Use the existing visual patterns from the rest of the catalog page (rounded-xl border, astra-surface backgrounds, amber/red/green accent colors).

### 4.5 Verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke:

1. Open `/catalog`. Suppliers tab: Wardstone shows with "In House" badge.
2. Parts tab: "Upload STEP" button visible next to "New Part".
3. Click "Upload STEP", pick the McMaster fixture from your local disk. Wait for the upload to complete. Page navigates to `/catalog/pending-imports/<id>`.
4. Review page renders with extracted data: manufacturer=McMaster-Carr, part_number=92196A196, material_name="18-8 Stainless Steel", material_class=stainless_steel, part_class=fastener_screw, part_subtype=socket_head_cap_screw, bounding box populated. Banner says "Linked to supplier McMaster-Carr". Confidence pills mostly green.
5. Click "Approve & Create Part". Page navigates to `/catalog/parts/<new id>` showing the new catalog part.
6. Suppliers tab: McMaster-Carr now exists alongside Wardstone.
7. Re-upload the same file → 409 dedup error visible in UI.
8. Upload a *different* McMaster STEP filename (or rename the file with a different MPN prefix and try) → reuses the existing McMaster-Carr supplier (no new row).

Commit: `phase-4(catalog-step): frontend Upload STEP + pending-imports review page`

---

## Out of scope — do NOT do these

1. **Don't refactor the existing PDF/datasheet/ICD extraction flow.** That's `app/services/catalog/icd_extractor.py` and the existing `POST /catalog/documents/{id}/extract` background trigger. STEP files use a parallel inline flow via the new `/catalog/upload-step` endpoint. Keep them separate.
2. **Don't install pythonOCC in the Docker image.** Graceful fallback covers the gap; image rebuild is a separate operational task.
3. **Don't change the existing `Supplier`, `SupplierDocument`, `CatalogPart`, `CatalogConnector`, `CatalogPin`, `PendingCatalogImport` table shapes.** Only ADD columns/values per the migration.
4. **Don't create a parallel `pending_imports` table or `supplier_documents` table.** The previous attempt did this and conflicted with reality. Use the existing tables.
5. **Don't touch System Architecture, Mechanical Interfaces, or Electrical Interfaces.** Those are separate TDDs.
6. **Don't auto-issue HAROLD-format part numbers.** Catalog `part_number` stays as the manufacturer's MPN. HAROLD nomenclature integration is a separate TDD.
7. **Don't redesign the existing `/catalog/page.tsx` layout.** Minor additions only (new button, badge, click-through). The existing three-tab table layout works.
8. **Don't drop or modify the legacy `pending_parts_imports` table.** It's the old library_parts pipeline being phased out; touching it is out of scope.

---

## Common gotchas

1. **`ALTER TYPE ADD VALUE` outside transaction.** PostgreSQL forbids enum value adds inside a transaction. Use `op.get_context().autocommit_block()` per the pattern in `0028_add_l0_level.py`. Forgetting this gives a confusing "ALTER TYPE ... cannot run inside a transaction block" error.

2. **CARTESIAN_POINT regex with scientific notation.** STEP files use `1.000000000000000082E-05`. Your bbox-extracting regex must match `[+-]?\d+\.?\d*([eE][+-]?\d+)?`. A naive `\d+\.?\d*` loses precision and misses negatives.

3. **STEP unit conversion.** McMaster files are typically inches (LENGTH_MEASURE_WITH_UNIT factor `0.0254` m = 1 inch). Multiply raw CARTESIAN_POINT values by `25.4` to get mm. SolidWorks-from-mm files use factor `0.001` (multiply by `1.0`). Don't hard-code `25.4`.

4. **Filename with spaces.** The McMaster fixture filename has spaces. Strip path, take basename, normalize whitespace before regex. `Path(file_path).name` then maybe `.replace(' ', '_')` for matching.

5. **Material lexicon longest-match-wins.** "18-8 Stainless Steel" must match before "Stainless Steel" (a substring). Sort aliases by length descending before matching, OR use word-boundary regex.

6. **Part-type lexicon ordering.** "Socket Head Cap Screw" must beat "Screw" alone. Same longest-match rule.

7. **SQLAlchemy enum value insertion.** Direct SQL inserts must use the lowercase enum value (`'fastener_screw'`), not the Python enum name (`'FASTENER_SCREW'`). Same when seeding the migration.

8. **JSONB defaults in raw SQL.** Postgres requires `'{}'::jsonb` not `'{}'`. Forgetting the cast causes silent text-column behavior.

9. **Multipart/form-data with FastAPI.** Use `File(...)` from `fastapi`. Don't try to load the entire file into memory if it's large; stream to disk via `await file.read()` then `path.write_bytes(content)` is fine for most STEP files (typically < 10MB) but for assemblies that hit 50MB+, switch to chunked reads.

10. **Audit log payload.** When auto-creating a supplier, the audit `details` dict must be JSON-serializable — the `detected_supplier_aliases` field is a list of strings, fine. But don't include the raw extracted_data JSONB (could be large) — link by IDs instead.

11. **Existing CatalogPart `part_class` is NOT NULL.** The new mechanical values must be supplied on every catalog part create. The STEP upload flow always derives one (defaulting to `mechanical_other` if the lexicon misses), so this is fine — but make sure manual `POST /catalog/parts` callers haven't been broken by enum extension. The existing values still work.

12. **The McMaster fixture file might not be where Claude Code expects.** Check `backend/tests/fixtures/cad/`. If missing, the relevant test should `pytest.skip()` with a clear message — don't hard-fail.

13. **`supplier_aliases.alias` UNIQUE means cross-supplier conflicts.** If McMaster-Carr is created with alias "MCMASTER", and someone later creates a different supplier "MCMASTER Inc." that wants alias "MCMASTER", the second insert raises IntegrityError. Handle this gracefully in the auto-create path: if alias insert fails, skip that alias and continue (don't roll back the whole supplier creation).

14. **Frontend: don't forget the multipart Content-Type header.** Axios will set the boundary automatically only if you DON'T set the header manually. Setting `headers: { 'Content-Type': 'multipart/form-data' }` works in most setups but if uploads break, try removing the header entirely and let Axios infer.

---

## Sign-off

After Phase 4:

```powershell
docker compose exec backend python -m pytest tests/test_step_parser.py tests/test_supplier_aliases.py tests/test_step_upload_flow.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → ensure the four phase commits are in place. Then write `docs/PHASE_CATALOG_STEP_NOTES.md` with:

- Per-AC status (the McMaster validation table from the "Validation fixture" section above, plus tests passing).
- Any deviations from this prompt with justification.
- Open follow-ups deferred (pythonOCC Docker image install, vendor seed CSV expansion, HAROLD nomenclature wiring, full Phase-7 ICD review UI parity).

If anything in this prompt conflicts with what you find in the existing code, **stop and surface the conflict** with a recommended resolution — do not guess, and do not refactor existing code that's outside scope. Especially: do not modify the existing `app/services/catalog/icd_extractor.py`, `app/services/catalog/placement.py`, the existing PendingCatalogImport approval logic in the catalog router, or any of the existing catalog frontend tab table layouts.

---

*Prompt version 2.0 — supersedes the earlier `CLAUDE_CODE_PROMPT_CAT-001.md` which was based on incorrect assumptions about the existing schema.*
