"""
ASTRA — ICD Extraction Prompts (Phase 7, ASTRA-TDD-INTF-002)
=============================================================
File: backend/app/services/catalog/prompts.py   ← NEW

Defines the system prompt + user-prompt template that ask the LLM to extract
structured catalog-part data from a pre-extracted supplier document
(PDF/DOCX/XLSX). The expected output JSON shape is the
:class:`app.schemas.catalog.IcdExtractionResultSchema` Pydantic model — that
schema is the contract; this prompt is the carrier.

Spec reference
--------------
The v1.1 spec §10 defers the prompt details to "v1.0" which is not present
in the repository (digest §10 anomaly #8). This module supplies a defensible
strict-JSON-schema prompt: the LLM is told (a) the exact schema, (b) the
fields to extract, (c) to cite source pages, (d) to use ``null`` rather
than invent values, and (e) to output ONLY JSON (no prose). Pydantic then
validates the response on the way back; mismatches mark the extraction
``FAILED`` with the validation error captured in ``extraction_log``.

Document size guard
-------------------
A real datasheet's text can run several hundred kilobytes. The
``MAX_DOC_TEXT_CHARS`` cap below truncates the embedded text + table dumps
in the user prompt; oversize content is replaced with a "[... truncated]"
marker. Truncation surfaces as a warning on the resulting
``PendingCatalogImport.extraction_warnings`` blob.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:    # pragma: no cover
    from app.services.catalog.document_extractor import ExtractedDocument


# ──────────────────────────────────────────────────────────────
#  Hard caps to keep the prompt bounded
# ──────────────────────────────────────────────────────────────

MAX_DOC_TEXT_CHARS: int = 80_000      # ~20-30 pages of dense datasheet text
MAX_TABLES_PER_PAGE: int = 4          # avoid runaway table sprawl
MAX_TABLE_ROWS: int = 60              # camelot can occasionally over-stretch


# ──────────────────────────────────────────────────────────────
#  System prompt
# ──────────────────────────────────────────────────────────────

ICD_EXTRACTION_SYSTEM_PROMPT: str = """\
You are a senior aerospace systems engineer extracting structured data from
a supplier ICD (Interface Control Document) or component datasheet.

You MUST output ONLY a single valid JSON object that matches the provided
schema exactly. No prose. No markdown fences. No commentary.

Rules:
1. Do NOT invent fields. If a value is not present in the source, use null.
2. Do NOT guess physical specs. Only emit a value when you see it in the text.
3. Cite the source page in the ``source_page`` field for every extracted
   value where the schema allows. Page numbers refer to the [P:N] markers
   embedded in the document text.
4. Use the canonical SI units the schema requires (kg, mm, V, A, °C, etc.).
5. Convert ranges like ``"-40 to +85 °C"`` into the matching min/max field
   pair. Convert "28 V ±10%" into voltage_min_v=25.2 and voltage_max_v=30.8.
6. When a connector pinout table appears, extract every row into the
   ``pins`` array — do not summarise. Match each row's pin number to
   ``pin_position`` and the signal name to ``mfr_pin_name``.
7. ``part_class`` and ``lru_classification`` are constrained enums; pick
   the closest valid value. Default ``lru_classification`` to "lru" if
   unclear.
8. If you find conflicting values across pages, prefer the most recent
   revision page and add a note in ``extraction_warnings``.
9. Unsupported / unknown document layouts: still output a JSON object with
   the supplier name and part_number you can find, and put a description
   of the limitation in ``extraction_warnings``. NEVER silently drop the
   request.
"""


# ──────────────────────────────────────────────────────────────
#  User prompt template
# ──────────────────────────────────────────────────────────────

_USER_PROMPT_TEMPLATE: str = """\
Extract a single supplier-catalog-part record from the document below.

Required output schema (strict JSON):
```
{schema_json}
```

Fields you MUST attempt to populate when present:

* ``supplier``: name (required), cage_code, country.
* ``part_number`` (required), ``revision``, ``name`` (required),
  ``description``, ``part_class`` (enum), ``lru_classification`` (enum).
* Physical: mass_kg, dim_length_mm, dim_width_mm, dim_height_mm.
* Power: power_watts_nominal, power_watts_peak, voltage_input_min_v,
  voltage_input_max_v.
* Environmental envelope: temp_operating_min_c / max_c,
  temp_storage_min_c / max_c, vibration_random_grms, shock_mechanical_g,
  humidity_max_pct, altitude_max_m, emi_ce102_limit_dbua,
  emi_rs103_limit_vm, esd_hbm_v.
* Compliance: mil_std_810_tested, mil_std_461_tested, rohs_compliant,
  itar_controlled, export_classification.
* Lifecycle: lifecycle_status (enum), eol_date.
* Connectors[]: each with reference (e.g. "J1"), description,
  connector_type (e.g. "MIL-DTL-38999/III"), shell_size, gender (enum),
  pin_count, and a ``pins`` array.
* Pins[]: pin_position (e.g. "1", "A1"), mfr_pin_name (required),
  mfr_signal_function, mfr_signal_type (enum: power/ground/digital/
  analog/diff_pair/rf/discrete/no_connect/reserved/unknown),
  mfr_direction (enum: input/output/bidirectional/power/ground/unknown),
  mfr_voltage_min_v, mfr_voltage_max_v, mfr_current_max_ma,
  mfr_impedance_ohm, mfr_protocol_hint.
* extraction_warnings: list of issues / ambiguities / truncation notes.
* extraction_confidence: 0.0-1.0 self-assessed.

Document type: {document_type}
Document pages: {page_count}{truncation_marker}

Document content (page markers as [P:N]):
{document_text}
"""


# ──────────────────────────────────────────────────────────────
#  Public helpers
# ──────────────────────────────────────────────────────────────

def render_document_for_prompt(
    extracted: "ExtractedDocument",
) -> Tuple[str, List[str]]:
    """Flatten an ExtractedDocument into a string with [P:N] page markers.

    Returns ``(text, warnings)`` where warnings record any truncation we did.
    """
    warnings: List[str] = []
    chunks: List[str] = []
    running_chars = 0
    truncated = False

    for page in extracted.pages:
        if truncated:
            break
        header = f"\n[P:{page.page_number}]\n"
        # Tables — render as TSV-ish for compactness
        table_chunks: List[str] = []
        for tbl in page.tables[:MAX_TABLES_PER_PAGE]:
            rows = tbl[:MAX_TABLE_ROWS]
            if not rows:
                continue
            table_chunks.append("[TABLE]\n" + "\n".join(
                "\t".join(cell.replace("\n", " ").strip() for cell in row)
                for row in rows
            ) + "\n[/TABLE]")
        page_text = page.text or ""
        page_str = header + page_text
        if table_chunks:
            page_str += "\n" + "\n".join(table_chunks)

        if running_chars + len(page_str) > MAX_DOC_TEXT_CHARS:
            # Take what we can fit
            allowed = MAX_DOC_TEXT_CHARS - running_chars
            if allowed > 200:
                chunks.append(page_str[:allowed] + "\n[... truncated, prompt cap reached]")
            else:
                chunks.append(f"\n[... truncated at page {page.page_number}, prompt cap reached]")
            warnings.append(
                f"Prompt truncated at page {page.page_number} of {extracted.page_count}; "
                "downstream review may need the original document"
            )
            truncated = True
            break

        chunks.append(page_str)
        running_chars += len(page_str)

    return "".join(chunks), warnings


def build_user_prompt(
    extracted: "ExtractedDocument",
    *,
    schema_json: str,
) -> Tuple[str, List[str]]:
    """Render the full user prompt; returns (prompt, warnings)."""
    document_text, warnings = render_document_for_prompt(extracted)
    truncation_marker = ""
    if extracted.truncated:
        truncation_marker = (
            f" (only first {len(extracted.pages)} of {extracted.page_count} extracted)"
        )
    prompt = _USER_PROMPT_TEMPLATE.format(
        schema_json=schema_json,
        document_type=extracted.document_type,
        page_count=extracted.page_count,
        truncation_marker=truncation_marker,
        document_text=document_text,
    )
    return prompt, warnings


def build_extraction_prompts(
    extracted: "ExtractedDocument",
    *,
    schema_json: str,
) -> Tuple[str, str, List[str]]:
    """Build the (system, user) prompt pair plus any prompt-time warnings."""
    user_prompt, warnings = build_user_prompt(extracted, schema_json=schema_json)
    return ICD_EXTRACTION_SYSTEM_PROMPT, user_prompt, warnings


def schema_json_repr(model_cls) -> str:
    """Compact JSON representation of a Pydantic model's JSON schema, used
    in the user prompt. Indented for readability when humans inspect the
    prompt body in audit logs."""
    return json.dumps(model_cls.model_json_schema(), indent=2)
