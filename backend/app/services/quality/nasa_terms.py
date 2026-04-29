"""
ASTRA — NASA Appendix C Prohibited Terms (single source of truth)
=================================================================
File: backend/app/services/quality/nasa_terms.py

Both ``services.quality_checker`` and ``services.reports.quality_report``
must import from this module. Any future quality-related tooling should
do the same.

Covers AUDIT_FINDINGS F-079.
"""

# NASA SP-2016-6105 Rev2 Appendix C — prohibited unverifiable / ambiguous terms.
# Sorted, deduplicated, single canonical list. Merged from the two prior
# divergent lists in ``quality_checker.py`` and ``reports/quality_report.py``.
PROHIBITED_TERMS: tuple[str, ...] = (
    "accommodate",
    "ad hoc",
    "adequate",
    "and/or",
    "appropriate",
    "as applicable",
    "as appropriate",
    "as needed",
    "as required",
    "be able to",
    "be capable of",
    "but not limited to",
    "capability of",
    "clearly",
    "easily",
    "easy",
    "effective",
    "effectively",
    "efficiently",
    "etc",
    "fast",
    "flexible",
    "if practical",
    "if required",
    "large",
    "light-weight",
    "lightweight",
    "maximize",
    "minimize",
    "normal",
    "portable",
    "provide for",
    "quickly",
    "reasonable",
    "robust",
    "safe",
    "simply",
    "small",
    "sufficient",
    "suitable",
    "timely",
    "usable",
    "user friendly",
    "user-friendly",
    "when required",
)

# Ambiguous quantifiers — separated from prohibited terms because the
# editorial check treats them as suggestions rather than warnings.
AMBIGUOUS_QUANTIFIERS: tuple[str, ...] = (
    "about",
    "approximately",
    "considerable",
    "few",
    "generally",
    "many",
    "minimal",
    "normally",
    "often",
    "several",
    "significant",
    "some",
    "usually",
)

# Placeholder values that must be resolved before baselining.
TBD_TERMS: tuple[str, ...] = ("TBD", "TBR")
