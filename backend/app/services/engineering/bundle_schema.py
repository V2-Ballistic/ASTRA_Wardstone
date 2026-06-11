"""
ASTRA — CITADEL Config Bundle v1 schema (canonical shared contract)
====================================================================
File: backend/app/services/engineering/bundle_schema.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §1)

THE canonical definition of the ``citadel-config-bundle/1.0``
``manifest.json`` contract. CITADEL mirrors this module — field names
here ARE the JSON keys (camelCase + unit-suffixed), so a validated
``Manifest`` dumps byte-for-byte to the wire format via
``manifest_to_dict()`` (``model_dump(mode="json", by_alias=True)``).

Determinism is the load-bearing property: the same config revision
must always produce the same ``bundleHash``. That is guaranteed by
``canonical_json`` (sorted keys, compact separators, NaN rejected) +
``compute_bundle_hash`` (hash computed over the manifest with the
``bundle.bundleHash`` field nulled, since the hash cannot include
itself).

Pydantic v2 throughout. ``extra="forbid"`` on every block — this is a
versioned contract; unknown keys mean a schema mismatch, not forward
compatibility (a new field is a new schema version).
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_ID = "citadel-config-bundle/1.0"

# ── Shared scalar / vector types ───────────────────────────────────

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Vec3 = Annotated[List[float], Field(min_length=3, max_length=3)]
Mat3 = Annotated[List[Vec3], Field(min_length=3, max_length=3)]
Range2 = Annotated[List[float], Field(min_length=2, max_length=2)]

#: Component roles (spec §1). Closed set — "other" is the escape hatch.
Role = Literal[
    "oml", "structure", "avionics", "payload",
    "propulsion", "recovery", "ballast", "other",
]


class _Block(BaseModel):
    """Base for every manifest block: strict (no unknown keys),
    alias-populatable (the ``schema`` field uses an alias)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ── Blocks ─────────────────────────────────────────────────────────

class BundleBlock(_Block):
    id: str
    createdUtc: str
    createdBy: str
    astraBaselineId: Optional[int] = None
    astraBaselineRev: Optional[str] = None
    #: sha256 of the canonical manifest WITH this field nulled — see
    #: ``compute_bundle_hash``. Optional only so the pre-hash manifest
    #: validates; a finished bundle always carries it.
    bundleHash: Optional[Sha256Hex] = None


class ConfigBlock(_Block):
    wpn: str
    name: str
    rev: str
    description: Optional[str] = None
    topAssemblyWpn: Optional[str] = None


class FrameBlock(_Block):
    """Stamped from the Frame ICD (spec §3) — icdId is the ICD key
    (e.g. 'citadel-vehicle-body-frame'), icdRev the immutable revision
    number the bundle's vectors are expressed against."""
    icdId: str
    icdRev: int
    datum: str
    axes: str
    units: str


class MassPropertiesBlock(_Block):
    totalMass_kg: float
    cg_m_B: Vec3
    inertia_kgm2_B: Mat3
    referencePoint_m_B: Vec3
    method: Literal["parallel_axis"] = "parallel_axis"


class ArtifactRef(_Block):
    type: str
    file: str
    sha256: Sha256Hex
    sourceSystem: str
    ingestUtc: str
    qualityTier: Optional[str] = None
    origin: Optional[str] = None
    designProvenanceId: Optional[str] = None


class ComponentEntry(_Block):
    role: Role
    wpn: str
    rev: str
    name: str
    mass_kg: float
    cg_m_B: Vec3
    inertia_kgm2_B: Mat3
    placement: Optional[Dict[str, Any]] = None
    artifact: ArtifactRef


class ValidityEnvelope(_Block):
    machRange: Range2
    alphaRange_deg: Range2
    betaRange_deg: Range2


class AeroBlock(_Block):
    wpn: str
    rev: str
    omlWpn: str
    Sref_m2: float
    Lref_m: float
    refPoint_m_B: Vec3
    validityEnvelope: ValidityEnvelope
    artifact: ArtifactRef


class PropulsionStage(_Block):
    stageNum: int
    motorWpn: str
    motorRev: str
    ignitionTime_s: float
    thrustAxis_B: Vec3
    mcTrialId: Optional[str] = None
    artifact: ArtifactRef


class Dependency(_Block):
    wpn: str
    rev: str
    sha256: Sha256Hex


class AstraProvenance(_Block):
    baselineId: Optional[int] = None
    exportedBy: str
    exportedUtc: str


class ProvenanceBlock(_Block):
    harold: Dict[str, Any] = Field(default_factory=dict)
    astra: AstraProvenance


class Manifest(_Block):
    """``manifest.json`` — schema id ``citadel-config-bundle/1.0``.

    The ``schema`` JSON key is exposed as the ``schema_`` attribute
    (``schema`` shadows a BaseModel classmethod); always serialize via
    ``manifest_to_dict()`` / ``model_dump(by_alias=True)`` so the wire
    key stays ``schema``.
    """
    schema_: Literal["citadel-config-bundle/1.0"] = Field(
        default=SCHEMA_ID, alias="schema",
    )
    bundle: BundleBlock
    config: ConfigBlock
    frame: FrameBlock
    massProperties: MassPropertiesBlock
    components: List[ComponentEntry] = Field(default_factory=list)
    aero: Optional[AeroBlock] = None
    propulsion: Optional[List[PropulsionStage]] = None
    recommendedFidelity: Optional[str] = None
    dependencies: List[Dependency] = Field(default_factory=list)
    provenance: ProvenanceBlock


def manifest_to_dict(manifest: Manifest) -> Dict[str, Any]:
    """JSON-mode dict of *manifest* using wire keys (``schema``)."""
    return manifest.model_dump(mode="json", by_alias=True)


# ── Determinism helpers ────────────────────────────────────────────

def sha256_bytes(data: bytes) -> str:
    """Lowercase hex sha256 of *data*."""
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON encoding: sorted keys, compact separators
    (no whitespace), UTF-8, NaN/Infinity rejected (``allow_nan=False``
    — non-finite floats have no canonical JSON form and would silently
    break cross-implementation hashing).

    Two structurally equal objects ALWAYS yield identical bytes,
    regardless of dict insertion order.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def compute_bundle_hash(manifest_dict: Dict[str, Any]) -> str:
    """sha256 of ``canonical_json`` of the manifest dict WITH
    ``bundle.bundleHash`` nulled.

    The hash cannot include itself, so the canonical form is defined
    as the manifest with ``bundle.bundleHash = null`` — verification
    re-nulls the field and recomputes. The input dict is NOT mutated.
    Same config rev ⇒ same canonical bytes ⇒ same bundleHash.
    """
    scrubbed = copy.deepcopy(manifest_dict)
    bundle = scrubbed.get("bundle")
    if isinstance(bundle, dict):
        bundle["bundleHash"] = None
    return sha256_bytes(canonical_json(scrubbed))


# ── Naming helpers ─────────────────────────────────────────────────

def bundle_dirname(config_wpn: str, config_rev: str, bundle_hash: str) -> str:
    """``<configWpn>_<configRev>_<bundleHash8>`` — the on-disk bundle
    directory name (first 8 hex chars of the bundle hash)."""
    return f"{config_wpn}_{config_rev}_{bundle_hash[:8]}"


#: Allowed artifact filename suffixes (spec §1).
ARTIFACT_SUFFIXES = ("massprops.yaml", "motor.json", "aero.json", "mesh.glb")


def artifact_filename(sha256: str, suffix: str) -> str:
    """``<sha256>.<suffix>`` content-addressed artifact filename.
    *suffix* must be one of ``ARTIFACT_SUFFIXES``."""
    if suffix not in ARTIFACT_SUFFIXES:
        raise ValueError(
            f"Unknown artifact suffix {suffix!r}; expected one of "
            f"{list(ARTIFACT_SUFFIXES)}"
        )
    return f"{sha256}.{suffix}"
