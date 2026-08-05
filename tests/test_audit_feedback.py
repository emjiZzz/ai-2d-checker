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
from services.backend.infrastructure.knowledge.auto_doc import AutoDocEngine
from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager


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


@pytest.mark.asyncio
async def test_autodoc_writes_a_learned_rule_note_into_the_vault(tmp_path):
    """The Pillar 3 write half of the feedback loop.

    `AutoDocEngine` reaches for `VaultSyncManager.get_instance()` rather than taking a
    manager, so the singleton's path is swapped and restored. Injecting it properly would be
    the better shape, but that is a production change and this test exists to establish the
    current behaviour first.
    """
    feedback = AuditFeedbackDocument.model_construct(
        session_id="sess_latest",
        drawing_id="dwg_001",
        client_name="TestClient",
        entity_text="TEST_PATTERN_999",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
    )

    manager = VaultSyncManager.get_instance()
    original_path = manager.vault_path
    manager.vault_path = tmp_path
    try:
        assert await AutoDocEngine.process_feedback_event(feedback) is True

        rule_file = tmp_path / "08 - Client Domain & CAD Rules" / "Learned_Rules_TestClient.md"
        assert rule_file.exists(), (
            "AutoDocEngine reported success but wrote nothing. The rule note is what "
            "vault_sync reads back into safe_filter — no file means the loop is open."
        )
        assert "TEST_PATTERN_999" in rule_file.read_text(encoding="utf-8")
    finally:
        manager.vault_path = original_path


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
