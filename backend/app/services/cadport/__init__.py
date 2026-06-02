"""CADPORT-side ASTRA services.

CADPORT-TDD-STEP-001 §7.1.4 introduces this package for the
post-import mass-edit flow:

  - mass_recompute       — linear inertia scaling identity, shared
                           with the CADPORT plugin's services/
                           mass_recompute.py (same math).
  - assembly_rerollup    — re-aggregates an assembly's mass / CG /
                           inertia from the current state of its
                           components (catalog_parts × cadport_
                           assembly_components.transform_json) via
                           standard rigid-body composition.
"""
