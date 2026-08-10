"""R1 — the `lessons` write path, pinned by reading the record back.

**Why this file exists, specifically.** The path it covers was written once, never worked, and
was never noticed. `audits.py` called `provider.embed_text(...)` — singular — against a provider
defining only `embed_texts`, so an `AttributeError` fired on the first line of a `try` whose
`except Exception` logged a warning and returned 200. The `lessons_learned` collection was never
written a single record. The endpoint's test asserted the request succeeded, which it always did.
See [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]].

So the rule this file enforces is the one that gotcha ends on: **assert that a write wrote, not
that it did not throw.** Every test below performs the write and then reads the record back out of
the index by querying for it. None of them assert "no exception was raised".

The second rule is structural. The endpoint's exception guard must not catch `AttributeError` —
that is the specific class of bug that hid here for months, and a guard broad enough to swallow a
misspelled method name will swallow one again.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import UTC, datetime

import pytest

from services.backend.api.routers import audits
from services.backend.domain.models.audit_violation import (
    RESOLUTION_APPROVED,
    RESOLUTION_REJECTED,
    AuditViolation,
)
from services.backend.infrastructure import retrieval
from services.backend.infrastructure.retrieval import service as retrieval_service

pytestmark = pytest.mark.asyncio


def _violation(
    vid: str,
    category: str,
    description: str,
    resolution: str | None,
    remarks: str = "",
) -> AuditViolation:
    violation = AuditViolation.model_construct(
        audit_session_id="session-1",
        severity="high",
        category=category,
        description=description,
        recommendation="Add the missing dimension callout to the affected view.",
        source="rule_engine",
        resolution_type=resolution,
        is_resolved=resolution == RESOLUTION_APPROVED,
        resolved_at=datetime.now(UTC),
        checker_remarks=remarks,
    )
    violation.id = vid
    return violation


@pytest.fixture
def stub_violations(monkeypatch):
    """Replace the Mongo query with an in-memory set, honouring the resolution_type filter.

    `AuditViolation.resolution_type` at class level is a Beanie field accessor that only exists
    after `init_beanie`, so it raises `AttributeError` offline. Same `MockField` shim as
    `test_standards_loader_async.py`, and note what it buys: the fixture reads the value out of
    the comparison rather than assuming it, so the `RESOLUTION_APPROVED` filter is genuinely
    under test instead of being hardcoded on both sides.
    """
    store: list[AuditViolation] = []

    class Comparison:
        def __init__(self, field, value):
            self.field, self.value = field, value

    class MockField:  # noqa: PLW1641 — __eq__ builds a query object; this is never hashed
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return Comparison(self, other)

    # raising=False because the attribute does not exist until Beanie is initialised. This also
    # makes monkeypatch *remove* it on teardown, where the older `MockField` shim in
    # test_standards_loader_async.py assigns directly and leaks the stub onto the class.
    monkeypatch.setattr(
        AuditViolation, "resolution_type", MockField("resolution_type"), raising=False
    )

    class MockQuery:
        def __init__(self, wanted):
            self._wanted = wanted

        def limit(self, _n):
            return self

        async def to_list(self):
            return [v for v in store if v.resolution_type == self._wanted]

    def fake_find(cls, comparison, *args, **kwargs):
        return MockQuery(getattr(comparison, "value", RESOLUTION_APPROVED))

    monkeypatch.setattr(AuditViolation, "find", classmethod(fake_find))
    return store


async def test_a_confirmed_finding_is_retrievable_after_review(stub_violations, tmp_path):
    """The read-back. Write a lesson, then find it by querying the index."""
    stub_violations.append(
        _violation(
            "v1",
            "missing_dimension",
            "寸法 missing dimension on section view A-A",
            RESOLUTION_APPROVED,
            remarks="Confirmed by checker: the chamfer callout is genuinely absent.",
        )
    )

    result = await retrieval_service.rebuild_lessons_index(root=tmp_path)
    assert result.built and result.n_records == 1

    outcome = retrieval.query(
        "missing dimension 寸法", collection=retrieval.LESSONS, root=tmp_path
    )

    assert outcome.answered
    assert outcome.hits, "the confirmed finding must be retrievable — this is the read-back"
    assert outcome.hits[0].record.id == "v1"
    assert "section view A-A" in outcome.hits[0].record.text
    assert outcome.hits[0].record.section == "missing_dimension"


async def test_the_checkers_remarks_are_part_of_the_indexed_lesson(stub_violations, tmp_path):
    """The remark is the most valuable part — it is what a human actually said."""
    stub_violations.append(
        _violation(
            "v2",
            "invalid_layer",
            "Entity on layer TEMP",
            RESOLUTION_APPROVED,
            remarks="TEMP layer is never permitted on production sheets for this client.",
        )
    )

    await retrieval_service.rebuild_lessons_index(root=tmp_path)
    outcome = retrieval.query(
        "TEMP layer production", collection=retrieval.LESSONS, root=tmp_path
    )

    assert outcome.hits
    assert "never permitted on production sheets" in outcome.hits[0].record.text


async def test_a_rejected_finding_is_not_indexed_as_a_lesson(stub_violations, tmp_path):
    """A rejected finding is a false positive. Feeding it back teaches the opposite."""
    stub_violations.append(
        _violation("v3", "scale_ratio", "Invalid scale 1:11", RESOLUTION_REJECTED)
    )

    result = await retrieval_service.rebuild_lessons_index(root=tmp_path)

    assert not result.built, "nothing approved, so there is nothing to index"
    outcome = retrieval.query("scale 1:11", collection=retrieval.LESSONS, root=tmp_path)
    assert outcome.status is retrieval.IndexStatus.MISSING
    assert not outcome.answered


async def test_only_approved_findings_survive_the_filter(stub_violations, tmp_path):
    stub_violations.extend(
        [
            _violation("keep", "missing_dimension", "Genuine miss", RESOLUTION_APPROVED),
            _violation("drop", "missing_dimension", "Genuine miss", RESOLUTION_REJECTED),
            _violation("none", "missing_dimension", "Genuine miss", None),
        ]
    )

    result = await retrieval_service.rebuild_lessons_index(root=tmp_path)

    assert result.n_records == 1
    store = retrieval.store_for(retrieval.LESSONS, tmp_path)
    store.load()
    assert [r.id for r in store.records] == ["keep"]


async def test_a_violation_with_no_usable_text_is_skipped(stub_violations, tmp_path):
    """Empty text would be an unrankable record that dilutes idf for everything else."""
    blank = _violation("blank", "", "", RESOLUTION_APPROVED)
    blank.recommendation = ""
    stub_violations.append(blank)

    result = await retrieval_service.rebuild_lessons_index(root=tmp_path)
    assert not result.built


async def test_the_index_is_derived_and_survives_being_deleted(stub_violations, tmp_path):
    """The violations are the source of truth; the index is a cache of them.

    This is the structural fix for the R0 defect. The old code wrote lessons into a separate
    store nothing else populated, so a silent write failure was unrecoverable and undetectable.
    Deriving from records the application already keeps means a lost index is rebuildable.
    """
    stub_violations.append(
        _violation("v4", "missing_dimension", "寸法 missing on detail B", RESOLUTION_APPROVED)
    )

    await retrieval_service.rebuild_lessons_index(root=tmp_path)
    store = retrieval.store_for(retrieval.LESSONS, tmp_path)
    assert store.exists()

    for path in (store.matrix_path, store.records_path, store.manifest_path):
        path.unlink()
    assert retrieval.query("寸法", collection=retrieval.LESSONS, root=tmp_path).status is (
        retrieval.IndexStatus.MISSING
    )

    await retrieval_service.rebuild_lessons_index(root=tmp_path)
    recovered = retrieval.query("寸法 detail B", collection=retrieval.LESSONS, root=tmp_path)
    assert recovered.hits and recovered.hits[0].record.id == "v4"


def test_the_review_endpoint_does_not_swallow_programming_errors():
    """The guard around the rebuild must not catch `AttributeError`.

    This is the exact bug: a bare `except Exception` turned a misspelled method name into a
    silent permanent no-op. Asserted on the source because the property is about *which*
    exception types the handler names — there is no runtime behaviour to observe when the
    correct answer is "the error propagates and crashes a test".
    """
    source = textwrap.dedent(inspect.getsource(audits.review_violation))
    tree = ast.parse(source)

    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "the rebuild is expected to be guarded — did the call move?"

    for handler in handlers:
        caught = handler.type
        assert caught is not None, (
            "a bare `except:` in the review endpoint would hide the same class of defect that "
            "kept lessons_learned empty for months"
        )
        names = (
            [e.id for e in caught.elts if isinstance(e, ast.Name)]
            if isinstance(caught, ast.Tuple)
            else [caught.id] if isinstance(caught, ast.Name) else []
        )
        assert "Exception" not in names and "BaseException" not in names, (
            f"review_violation catches {names}. `except Exception` is what swallowed the "
            "AttributeError behind the original defect — catch what a rebuild can actually "
            "raise (OSError, ValueError, EncoderError) so a typo crashes instead of warning."
        )
