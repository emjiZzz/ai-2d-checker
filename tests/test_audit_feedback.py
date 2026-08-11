"""Stage 0g — relocated from `services/backend/tests/test_audit_feedback.py`, which had
**never executed** (outside `testpaths`, and its `infrastructure.*` imports fail collection
from the repo root).

`AuditFeedbackDocument` is the training substrate for the whole learned layer, and
`AutoDocEngine` is Pillar 3: it writes learned dismissal rules back into the vault, which
`vault_sync` then reads and feeds to `safe_filter`. That loop gates real output on the
default comparison path, and until now no test in the collected suite exercised the writing
half of it.
"""

from types import SimpleNamespace

import pytest

from services.backend.domain.models.audit_feedback import AuditFeedbackDocument
from services.backend.infrastructure.knowledge import auto_doc as auto_doc_module
from services.backend.infrastructure.knowledge.auto_doc import (
    MIN_DISMISSALS_TO_PROMOTE,
    AutoDocEngine,
    build_dismissal_filter,
)
from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager


def _dismissal(**overrides) -> AuditFeedbackDocument:
    """A dismissal feedback row, with sensible defaults."""
    fields = dict(
        session_id="sess_latest",
        drawing_id="dwg_001",
        client_name="TestClient",
        entity_text="TEST_PATTERN_999",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
    )
    fields.update(overrides)
    return AuditFeedbackDocument.model_construct(**fields)


@pytest.fixture
def counted(monkeypatch):
    """Replaces the dismissal count with a fixed number (or an exception).

    The suite has no MongoDB, so the real `count_client_dismissals` always raises. Before this
    fixture existed, the module's own `except` branch caught that and substituted the promotion
    threshold — which is why the pre-existing write test passed, and why the defect it was
    covering for went unnoticed. Stubbing the count explicitly is what lets a test distinguish
    "three dismissals" from "the database is down".
    """

    def _install(value):
        async def _fake(target_text, client_name):
            if isinstance(value, Exception):
                raise value
            return value

        monkeypatch.setattr(auto_doc_module, "count_client_dismissals", _fake)

    return _install


def test_feedback_document_carries_the_core_correction_fields():
    feedback = AuditFeedbackDocument.model_construct(
        session_id="session_123",
        drawing_id="drawing_456",
        client_name="KMTI",
        entity_text="12.5S",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
        human_comment="Surface roughness legend in title block",
    )
    assert feedback.session_id == "session_123"
    assert feedback.entity_text == "12.5S"
    assert feedback.human_corrected_status == "dismissed"


def test_feedback_document_carries_the_richer_correction_fields():
    """`finding_snapshot` is the fixed-shape payload the learned model trains on. Its three
    `null` features are correct by design — see
    [[Gotcha - Null Snapshot Features Are Not Degraded Labels]]."""
    feedback = AuditFeedbackDocument.model_construct(
        session_id="s",
        drawing_id="d",
        entity_text="ø25",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="verdict_matched",
        corrected_category=None,
        corrected_value="ø30",
        finding_snapshot={
            "rev_text": "ø25",
            "det_status": "CHANGED",
            "category": "drawing_views",
        },
    )
    assert feedback.human_corrected_status == "verdict_matched"
    assert feedback.corrected_value == "ø30"
    assert feedback.finding_snapshot["rev_text"] == "ø25"


@pytest.fixture
def vault_at(tmp_path):
    """Points the `VaultSyncManager` singleton at a temp dir for the duration of a test.

    `AutoDocEngine` reaches for `VaultSyncManager.get_instance()` rather than taking a manager,
    so the singleton's path is swapped and restored. Injecting it properly would be the better
    shape, but that is a production change these tests deliberately do not make.
    """
    manager = VaultSyncManager.get_instance()
    original_path = manager.vault_path
    manager.vault_path = tmp_path
    try:
        yield tmp_path
    finally:
        manager.vault_path = original_path


def _rule_file(root, client="TestClient"):
    return root / "08 - Client Domain & CAD Rules" / f"Learned_Rules_{client}.md"


@pytest.mark.asyncio
async def test_autodoc_writes_a_learned_rule_note_into_the_vault(vault_at, counted):
    """The Pillar 3 write half of the feedback loop."""
    counted(MIN_DISMISSALS_TO_PROMOTE)

    assert await AutoDocEngine.process_feedback_event(_dismissal()) is True

    rule_file = _rule_file(vault_at)
    assert rule_file.exists(), (
        "AutoDocEngine reported success but wrote nothing. The rule note is what "
        "vault_sync reads back into safe_filter — no file means the loop is open."
    )
    assert "TEST_PATTERN_999" in rule_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_autodoc_does_not_promote_below_the_threshold(vault_at, counted):
    counted(MIN_DISMISSALS_TO_PROMOTE - 1)

    assert await AutoDocEngine.process_feedback_event(_dismissal()) is False
    assert not _rule_file(vault_at).exists()


@pytest.mark.asyncio
async def test_a_database_error_never_promotes_a_dismissal(vault_at, counted):
    """The count used to fall back to exactly the promotion threshold on **any** exception, via
    `getattr(feedback, "_mock_dismiss_count", 3)` — test scaffolding reachable from the
    production path. One dismissal plus one database hiccup wrote a permanent rule that
    suppresses findings.

    A count that could not be taken is no information. It must never be evidence.
    """
    counted(RuntimeError("Mongo is unreachable"))

    assert await AutoDocEngine.process_feedback_event(_dismissal()) is False
    assert not _rule_file(vault_at).exists(), (
        "A database error promoted a dismissal to a permanent vault rule."
    )


@pytest.mark.asyncio
async def test_the_mock_dismiss_count_hook_is_gone(vault_at, counted):
    """Pins the removal of the hook itself, not just its default.

    An attribute set on the feedback *document* must not be able to influence promotion — that
    is the property that made the old fallback reachable from production in the first place.
    """
    counted(0)
    feedback = _dismissal()
    feedback._mock_dismiss_count = 99

    assert await AutoDocEngine.process_feedback_event(feedback) is False
    assert not _rule_file(vault_at).exists()


def test_the_dismissal_count_is_scoped_to_one_client():
    """The defect that made this the highest-severity open item: the count had no
    `client_name` clause while the rule was filed under `feedback.client_name`, so a pattern
    dismissed **once at each of three different clients** reached N>=3 and wrote customer A's
    verbatim drawing text into customer B's rule file. That is the cross-client contamination
    the retired two-tier overlay existed to prevent — nothing else prevents it now.
    """
    assert build_dismissal_filter("12.5S", "KMTI")["client_name"] == "KMTI"


def test_an_unattributed_dismissal_is_counted_against_other_unattributed_ones():
    """`client_name=None` files under "General", so it must be promoted by other unattributed
    dismissals — matched as `None`, not dropped from the filter (which would restore the
    sheet-wide count for exactly the rows that carry no client)."""
    f = build_dismissal_filter("12.5S", None)
    assert "client_name" in f and f["client_name"] is None


def test_retracted_dismissals_do_not_count_towards_a_permanent_rule():
    """A retraction is a human saying "I clicked that by mistake". `trainer.py` already skips
    retracted rows; this counter did not, so three taken-back clicks could write a rule that
    suppresses real findings forever — and a vault rule is far more durable than a training row.
    """
    assert build_dismissal_filter("12.5S", "KMTI")["retracted_at"] is None


def test_the_dismissal_filter_still_scopes_by_pattern_and_verb():
    f = build_dismissal_filter("12.5S", "KMTI")
    assert f["entity_text"] == "12.5S"
    assert f["human_corrected_status"] == "dismissed"


def test_bundle_builder_runs_offline_on_fake_feedback():
    """`build_bundle` is the trainer's pure half — no DB, so the learned layer is testable
    without Mongo. A single dismissal is remembered as an exact override even though 1 is
    far below `MIN_TRAIN`; that is the cold-start behaviour, not a bug."""
    from services.backend.infrastructure.learning.trainer import build_bundle

    docs = [
        SimpleNamespace(
            human_corrected_status="dismissed",
            category="drawing_views",
            entity_text="LEGEND",
            original_status="CHANGED",
            corrected_category=None,
            corrected_value=None,
            created_at=None,
            finding_snapshot={
                "rev_text": "LEGEND",
                "ref_text": "LEGEND",
                "category": "drawing_views",
            },
        )
    ]
    bundle = build_bundle(docs)

    assert bundle["n_total"] == 1
    assert bundle["exact_matched"]
