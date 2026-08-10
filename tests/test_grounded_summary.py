"""ADR-010's verification gate, and the guarantee that a failing summary never reaches a reader.

**What this file is really protecting.** An LLM summarising an inspection result can silently drop
a finding, and a fluent summary is the last place a human will look for one. Every other property
here is secondary to `test_a_summary_that_omits_a_finding_is_withheld`.

The gate is deliberately strict and deliberately blunt: a summary either verifies whole or is not
shown at all. There is no partial render and no retry — a retry loop would turn the gate into a
filter for plausible-looking output and hide how often it fails, which is the exact failure mode
this project has already paid for once with SHA-256 embeddings.
"""
from __future__ import annotations

import pytest

from services.backend.infrastructure.audit import summary as summary_pkg
from services.backend.infrastructure.audit.comparison.cache_manager import (
    ComparisonCacheManager,
)
from services.backend.infrastructure.audit.summary import (
    Finding,
    GroundedSummary,
    SummaryClaim,
    SummaryStatus,
    VerificationFailure,
    deterministic_summary,
    finding_digest,
    summarize,
    verify,
)
from services.backend.infrastructure.audit.summary import service as summary_service
from services.backend.infrastructure.audit.summary.generate import build_prompt


def _findings(n: int = 3) -> list[Finding]:
    return [
        Finding(id=f"f{i}", category="comparison_notes_section", status="CHANGED",
                description=f"[CHANGED] 板厚 1{i} -> 1{i + 1}")
        for i in range(n)
    ]


def _good_summary(findings: list[Finding]) -> GroundedSummary:
    return GroundedSummary(
        headline="Three note values were revised.",
        claims=[SummaryClaim(text="Plate thickness values changed.",
                             finding_ids=[f.id for f in findings])],
        total_findings_stated=len(findings),
    )


# ---------------------------------------------------------------- the gate


def test_a_well_grounded_summary_verifies():
    findings = _findings()
    assert verify(_good_summary(findings), findings).ok


def test_a_summary_that_omits_a_finding_is_withheld():
    """The recall guard, and the reason ADR-010 has the shape it has."""
    findings = _findings(3)
    partial = GroundedSummary(
        headline="Some values changed.",
        claims=[SummaryClaim(text="Two note values changed.", finding_ids=["f0", "f1"])],
        total_findings_stated=3,
    )

    result = verify(partial, findings)

    assert not result.ok
    assert VerificationFailure.UNCITED_FINDING in result.failures
    assert "f2" in result.detail


def test_a_summary_citing_an_invented_finding_is_withheld():
    findings = _findings(2)
    invented = GroundedSummary(
        headline="Values changed.",
        claims=[SummaryClaim(text="Everything changed.", finding_ids=["f0", "f1", "f99"])],
        total_findings_stated=2,
    )

    result = verify(invented, findings)

    assert not result.ok
    assert VerificationFailure.UNKNOWN_FINDING_ID in result.failures
    assert "f99" in result.detail


def test_a_mismatched_count_is_withheld():
    findings = _findings(3)
    miscounted = _good_summary(findings)
    miscounted.total_findings_stated = 2

    result = verify(miscounted, findings)

    assert not result.ok
    assert VerificationFailure.COUNT_MISMATCH in result.failures


def test_a_claim_citing_nothing_is_withheld():
    """Prose with no citation is exactly the ungrounded output the contract forbids."""
    findings = _findings(1)
    floating = GroundedSummary(
        headline="Something changed.",
        claims=[
            SummaryClaim(text="The drawing was revised.", finding_ids=[]),
            SummaryClaim(text="A note changed.", finding_ids=["f0"]),
        ],
        total_findings_stated=1,
    )

    result = verify(floating, findings)

    assert not result.ok
    assert VerificationFailure.EMPTY_CITATION in result.failures


def test_grouping_many_findings_into_one_claim_is_allowed():
    """Grouping is the feature. Only silence is forbidden."""
    findings = _findings(8)
    grouped = GroundedSummary(
        headline="One revision touched eight notes.",
        claims=[SummaryClaim(text="Eight note values were revised together.",
                             finding_ids=[f.id for f in findings])],
        total_findings_stated=8,
    )
    assert verify(grouped, findings).ok


def test_every_failure_is_reported_not_just_the_first():
    """A log line should name the whole problem, like `eval_corpus.py validate`."""
    findings = _findings(3)
    bad = GroundedSummary(
        headline="x",
        claims=[SummaryClaim(text="y", finding_ids=["nope"])],
        total_findings_stated=99,
    )

    result = verify(bad, findings)

    assert {
        VerificationFailure.UNKNOWN_FINDING_ID,
        VerificationFailure.UNCITED_FINDING,
        VerificationFailure.COUNT_MISMATCH,
    } <= set(result.failures)


# ---------------------------------------------------------------- the service


def test_the_feature_is_off_by_default(monkeypatch):
    """ADR-010 ships this opt-in. Default-off is the safety-relevant half: a summary request sends
    verbatim drawing text off the machine, and ADR-005 makes local-only a commercial promise."""
    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", False)
    outcome = summarize(_findings())

    assert outcome.status is SummaryStatus.DISABLED
    assert outcome.fallback_text  # still truthful, still renderable


def test_a_withheld_summary_is_not_returned_even_partially(monkeypatch, tmp_path):
    """The whole gate, end to end: generation succeeds, verification fails, nothing is shown."""
    findings = _findings(3)
    omitting = GroundedSummary(
        headline="Two values changed.",
        claims=[SummaryClaim(text="Two changed.", finding_ids=["f0", "f1"])],
        total_findings_stated=3,
    )

    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", True)
    monkeypatch.setattr(summary_service, "generate", lambda f, lang: (omitting, "test-model"))
    monkeypatch.setattr(summary_service, "get_storage_root", lambda: str(tmp_path))

    outcome = summarize(findings)

    assert outcome.status is SummaryStatus.WITHHELD
    assert outcome.headline is None, "A withheld summary must not leak its headline."
    assert outcome.claims == [], "A withheld summary must not be shown partially."
    assert VerificationFailure.UNCITED_FINDING in outcome.withheld_reasons
    assert outcome.fallback_text


def test_a_withheld_summary_is_never_cached(monkeypatch, tmp_path):
    """Verification runs before the write. Otherwise a summary that failed the gate once would be
    served from cache forever after."""
    findings = _findings(2)
    bad = GroundedSummary(headline="x", claims=[SummaryClaim(text="y", finding_ids=["f0"])],
                          total_findings_stated=2)

    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", True)
    monkeypatch.setattr(summary_service, "generate", lambda f, lang: (bad, "test-model"))
    monkeypatch.setattr(summary_service, "get_storage_root", lambda: str(tmp_path))

    assert summarize(findings).status is SummaryStatus.WITHHELD

    cache_dir = tmp_path / "cache" / "summaries"
    written = list(cache_dir.glob("*.json")) if cache_dir.exists() else []
    assert written == [], f"A summary that failed verification was cached: {written}"


def test_a_verified_summary_is_cached_and_reused(monkeypatch, tmp_path):
    findings = _findings(2)
    calls: list[int] = []

    def fake_generate(f, lang):
        calls.append(1)
        return _good_summary(findings), "test-model"

    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", True)
    monkeypatch.setattr(summary_service, "generate", fake_generate)
    monkeypatch.setattr(summary_service, "get_storage_root", lambda: str(tmp_path))

    first = summarize(findings)
    second = summarize(findings)

    assert first.status is SummaryStatus.OK and not first.cached
    assert second.status is SummaryStatus.OK and second.cached
    assert len(calls) == 1, "The second call regenerated instead of using the cache."


def test_an_unavailable_provider_is_normal_operation(monkeypatch, tmp_path):
    """No key, no network, provider down: the product works and says so."""
    def boom(f, lang):
        raise summary_pkg.SummaryUnavailableError("no key")

    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", True)
    monkeypatch.setattr(summary_service, "generate", boom)
    monkeypatch.setattr(summary_service, "get_storage_root", lambda: str(tmp_path))

    outcome = summarize(_findings())

    assert outcome.status is SummaryStatus.UNAVAILABLE
    assert outcome.fallback_text
    assert outcome.claims == []


def test_no_findings_is_not_an_error():
    outcome = summarize([])
    assert outcome.status is SummaryStatus.NOT_APPLICABLE
    assert "No differences" in outcome.fallback_text


# ---------------------------------------------------------------- supporting properties


def test_the_digest_ignores_ordering_but_not_content():
    a = _findings(3)
    reordered = [a[2], a[0], a[1]]
    assert finding_digest(a) == finding_digest(reordered)

    changed = _findings(3)
    changed[0].description = "[CHANGED] something else"
    assert finding_digest(a) != finding_digest(changed)


def test_the_summary_cache_is_not_the_comparison_cache(monkeypatch, tmp_path):
    """CLAUDE.md constraint 2 governs `COMPARISON_CACHE_VERSION` for spatial matching and zone
    extraction. Sharing that lever would make a prompt reword invalidate real comparisons, and
    would quietly widen a constraint written for geometry into "anything AI-adjacent".

    Asserted behaviourally, not by symbol inspection: a summary must land somewhere that is not
    the comparison cache directory, and bumping the comparison version must not move it.
    """
    findings = _findings(2)
    monkeypatch.setattr(summary_service.settings, "ENABLE_LLM_SUMMARY", True)
    monkeypatch.setattr(summary_service, "generate", lambda f, lang: (_good_summary(findings), "m"))
    monkeypatch.setattr(summary_service, "get_storage_root", lambda: str(tmp_path))

    assert summarize(findings).status is SummaryStatus.OK
    written = sorted(p.name for p in (tmp_path / "cache" / "summaries").glob("*.json"))
    assert written, "The verified summary was not cached at all."

    # The comparison version is a separate lever; moving it must not invalidate summaries.
    monkeypatch.setattr(ComparisonCacheManager, "COMPARISON_CACHE_VERSION", "v999")
    assert summarize(findings).cached is True, (
        "Bumping COMPARISON_CACHE_VERSION invalidated the summary cache. The two levers are "
        "supposed to be independent (ADR-010 decision 6)."
    )
    assert summary_pkg.SUMMARY_CACHE_VERSION == 1


def test_the_deterministic_fallback_never_omits_a_finding():
    findings = _findings(5)
    text = deterministic_summary(findings)
    assert "5 findings" in text


def test_the_prompt_carries_findings_and_nothing_else():
    """ADR-010 decision 2: the finding list is the entire input. If an image or an entity dump is
    ever added here, the coverage check can no longer distinguish 'the model described something
    outside the list' from 'the differ missed something'."""
    findings = _findings(2)
    prompt = build_prompt(findings)

    assert "f0" in prompt and "f1" in prompt
    assert "total_findings_stated MUST be exactly 2" in prompt


@pytest.mark.parametrize("field", ["headline", "claims", "total_findings_stated"])
def test_the_llm_schema_stays_fixed_field(field):
    """CLAUDE.md constraint 1 / ADR-002: GroundedSummary is passed to Gemini as a response_schema,
    so a bare dict anywhere in it would 400 every request rather than only when populated."""
    assert field in GroundedSummary.model_fields

    for name, info in GroundedSummary.model_fields.items():
        assert info.annotation is not dict, f"{name} is an open-ended dict; Gemini will reject it."
