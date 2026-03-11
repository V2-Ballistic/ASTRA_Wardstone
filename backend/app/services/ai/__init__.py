"""
ASTRA — AI Services Package
==============================
File: backend/app/services/ai/__init__.py   ← NEW

Central entry point.  All AI features are optional — the system
works fully with regex-only quality checks when no AI provider is
configured.
"""

from app.services.ai.llm_client import LLMClient, is_ai_available
from app.services.ai.quality_analyzer import (
    analyze_quality_deep,
    analyze_requirement_set,
)

__all__ = [
    "LLMClient",
    "is_ai_available",
    "analyze_quality_deep",
    "analyze_requirement_set",
]
