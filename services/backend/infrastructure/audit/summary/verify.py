"""The verification gate — ADR-010 decision 3, and the reason that ADR exists in this shape.

A generated summary is shown **only** if it passes every check here. On any failure the summary is
withheld entirely and the deterministic template renders in its place, visibly. It is never
partially shown, never truncated to the part that verified, and never silently retried until
something passes -- a retry loop would turn this gate into a filter for *plausible-looking* output
and hide the failure rate, which is the failure this whole track exists to correct.

**Why the strongest check is coverage, not fluency.** In an inspection tool a dropped finding is
the worst possible failure, and a fluent summary is the last place a human will look for one. So
the coverage check requires that the union of all cited ids covers **every** finding supplied. A
model that quietly omits the one finding that mattered fails here rather than reading as a clean
report.
"""
from __future__ import annotations

from .models import (
    Finding,
    GroundedSummary,
    VerificationFailure,
    VerificationResult,
)


def verify(summary: GroundedSummary, findings: list[Finding]) -> VerificationResult:
    """Check a generated summary against the findings it was built from.

    Returns every failure found rather than the first, so a log line names the whole problem --
    the same reason `tools/eval_corpus.py validate` reports all problems in one pass.
    """
    failures: list[VerificationFailure] = []
    details: list[str] = []

    supplied = {f.id for f in findings}

    if not summary.claims:
        failures.append(VerificationFailure.NO_CLAIMS)
        details.append("The summary contains no claims.")

    # 1. Every cited id must exist. An id the model invented is the clearest possible signal that
    #    it is describing something that is not in the finding list.
    cited: set[str] = set()
    unknown: set[str] = set()
    for claim in summary.claims:
        if not claim.finding_ids:
            if VerificationFailure.EMPTY_CITATION not in failures:
                failures.append(VerificationFailure.EMPTY_CITATION)
                details.append(f"A claim cites no findings: {claim.text[:80]!r}")
            continue
        for fid in claim.finding_ids:
            if fid in supplied:
                cited.add(fid)
            else:
                unknown.add(fid)

    if unknown:
        failures.append(VerificationFailure.UNKNOWN_FINDING_ID)
        details.append(f"Cited findings that do not exist: {sorted(unknown)}")

    # 2. Coverage -- the recall guard. A finding the model did not mention is a finding the reader
    #    will not see. Grouping is allowed (one claim may cite many ids); silence is not.
    uncited = supplied - cited
    if uncited:
        failures.append(VerificationFailure.UNCITED_FINDING)
        details.append(
            f"{len(uncited)} of {len(supplied)} findings are not mentioned by any claim: "
            f"{sorted(uncited)[:10]}"
        )

    # 3. The count the model echoed must match what it was given.
    #
    #    ADR-010 says "every stated count equals the real count". This enforces it on the
    #    STRUCTURED echo, not by parsing digits out of the prose, and the difference is
    #    deliberate: this domain's finding text is full of numbers that are not counts
    #    ("板厚 12 -> 14", "2-7キリ"), so a prose scan would withhold correct summaries on
    #    dimension values. A false withholding costs the user the feature, which is a real cost.
    #    Recorded as a deviation in ADR-010 rather than left as an unstated gap: this catches a
    #    model that lost track of its input, and does not catch a wrong number written mid-
    #    sentence. The coverage check above is the one carrying the weight.
    if summary.total_findings_stated != len(findings):
        failures.append(VerificationFailure.COUNT_MISMATCH)
        details.append(
            f"Summary states {summary.total_findings_stated} findings; "
            f"{len(findings)} were supplied."
        )

    return VerificationResult(
        ok=not failures,
        failures=failures,
        detail=" | ".join(details),
    )
