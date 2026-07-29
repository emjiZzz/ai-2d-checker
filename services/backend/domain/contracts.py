"""
contracts.py — Canonical domain data contracts for comparison auditing and physical CAD checks.
"""

from ..api.schemas import (
    CategoryComparison,
    CanvasMarking,
    CategoryAgreement,
    ComparisonDiagnostics,
    PhysicalComparisonResponse,
    ViewSummary,
    DrawingSummaryResponse,
)

__all__ = [
    "CategoryComparison",
    "CanvasMarking",
    "CategoryAgreement",
    "ComparisonDiagnostics",
    "PhysicalComparisonResponse",
    "ViewSummary",
    "DrawingSummaryResponse",
]
