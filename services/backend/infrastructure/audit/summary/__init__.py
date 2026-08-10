"""Grounded summarization of comparison findings — ADR-010.

An LLM composes prose about findings that **already exist**. It never decides what changed; that
is ADR-006's argument and it is not reopened here. Every generated summary passes a deterministic
verification gate before it can be displayed, and is withheld whole if it does not.

Public surface is `summarize()`. Everything else is an implementation detail, importable for tests.
"""
from .generate import SummaryUnavailableError, deterministic_summary
from .models import (
    Finding,
    GroundedSummary,
    SummaryClaim,
    SummaryOutcome,
    SummaryStatus,
    VerificationFailure,
    VerificationResult,
)
from .service import SUMMARY_CACHE_VERSION, finding_digest, summarize
from .verify import verify

__all__ = [
    "SUMMARY_CACHE_VERSION",
    "Finding",
    "GroundedSummary",
    "SummaryClaim",
    "SummaryOutcome",
    "SummaryStatus",
    "SummaryUnavailableError",
    "VerificationFailure",
    "VerificationResult",
    "deterministic_summary",
    "finding_digest",
    "summarize",
    "verify",
]
