"""Fixed-field shapes for grounded summarization (ADR-010).

Every model in this file that reaches Gemini as a `response_schema` must stay fixed-field.
A bare `dict` emits open-ended `additionalProperties`, which Gemini rejects with
`400 INVALID_ARGUMENT` on *every* request rather than only when the field is populated --
`CLAUDE.md` constraint 1, ADR-002. That is also why these live here instead of being nested into
`PhysicalComparisonResponse`: ADR-010 decision 5 keeps the summary schema decoupled from the
comparison schema for exactly the reason ADR-002 decoupled the zone bbox endpoint.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """One non-MATCHED comparison finding, as handed to the model.

    This is the *entire* input. No images, no raw entities, no retrieved prose -- ADR-010
    decision 2. An image would let the model describe something absent from this list, and the
    coverage check below could not distinguish that from a real omission by the differ.
    """

    id: str
    category: str
    status: str
    description: str


class SummaryClaim(BaseModel):
    """One sentence, plus the findings it rests on."""

    text: str = Field(..., description="A single sentence about the findings cited below.")
    finding_ids: list[str] = Field(
        ...,
        description="Ids of every finding this sentence is about. Must be non-empty and must "
        "only contain ids present in the supplied finding list.",
    )


class GroundedSummary(BaseModel):
    """The model's structured output. This is the Gemini `response_schema`."""

    headline: str = Field(..., description="One sentence stating the overall outcome.")
    claims: list[SummaryClaim] = Field(
        ..., description="Grouped observations. Every supplied finding must be cited by at least "
        "one claim."
    )
    total_findings_stated: int = Field(
        ...,
        description="The total number of findings you were given. Echo the number supplied to "
        "you; do not recount.",
    )


class SummaryStatus(StrEnum):
    OK = "ok"
    WITHHELD = "withheld"          # generated, failed verification -- see ADR-010 decision 3
    UNAVAILABLE = "unavailable"    # no key, no network, provider error
    DISABLED = "disabled"          # ENABLE_LLM_SUMMARY is off (the default)
    NOT_APPLICABLE = "not_applicable"  # nothing to summarize


class VerificationFailure(StrEnum):
    """Why a summary was withheld. Distinct values rather than a message, so a caller can branch
    and a test can assert on the reason rather than on prose."""

    UNKNOWN_FINDING_ID = "unknown_finding_id"
    UNCITED_FINDING = "uncited_finding"
    COUNT_MISMATCH = "count_mismatch"
    EMPTY_CITATION = "empty_citation"
    NO_CLAIMS = "no_claims"


class VerificationResult(BaseModel):
    ok: bool
    failures: list[VerificationFailure] = Field(default_factory=list)
    detail: str = ""


class SummaryOutcome(BaseModel):
    """What the service returns. Mirrors R1's `SearchOutcome` posture deliberately: "could not
    answer" is a distinct *value* from "nothing to report", so a caller cannot conflate them by
    accident. `fallback_text` is always populated, so a consumer always has something truthful to
    render regardless of status."""

    status: SummaryStatus
    headline: str | None = None
    claims: list[SummaryClaim] = Field(default_factory=list)
    fallback_text: str = ""
    withheld_reasons: list[VerificationFailure] = Field(default_factory=list)
    withheld_detail: str = ""
    finding_count: int = 0
    model_used: str | None = None
    cached: bool = False
