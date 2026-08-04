import pytest
from domain.models.audit_feedback import AuditFeedbackDocument
from infrastructure.knowledge.auto_doc import AutoDocEngine
from infrastructure.knowledge.vault_sync import VaultSyncManager

def test_audit_feedback_document_instantiation():
    """Verify AuditFeedbackDocument schema fields."""
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

@pytest.mark.asyncio
async def test_autodoc_engine_rule_writing(tmp_path):
    """Verify AutoDocEngine processes feedback events and writes rule notes on N >= 3 dismissals."""
    target_fb = AuditFeedbackDocument.model_construct(
        session_id="sess_latest",
        drawing_id="dwg_001",
        client_name="TestClient",
        entity_text="TEST_PATTERN_999",
        category="drawing_views",
        original_status="CHANGED",
        human_corrected_status="dismissed",
    )

    # Point vault path to tmp_path
    sync_mgr = VaultSyncManager.get_instance()
    old_vault_path = sync_mgr.vault_path
    sync_mgr.vault_path = tmp_path

    try:
        auto_doc_triggered = await AutoDocEngine.process_feedback_event(target_fb)
        assert auto_doc_triggered is True

        # Verify rule file written to vault
        rule_file = tmp_path / "08 - Client Domain & CAD Rules" / "Learned_Rules_TestClient.md"
        assert rule_file.exists()

        with open(rule_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "TEST_PATTERN_999" in content
    finally:
        sync_mgr.vault_path = old_vault_path


def test_audit_feedback_document_new_correction_fields():
    """The richer human-in-the-loop fields persist on the document."""
    fb = AuditFeedbackDocument.model_construct(
        session_id="s", drawing_id="d", entity_text="ø25", category="drawing_views",
        original_status="CHANGED", human_corrected_status="verdict_matched",
        corrected_category=None, corrected_value="ø30",
        finding_snapshot={"rev_text": "ø25", "det_status": "CHANGED", "category": "drawing_views"},
    )
    assert fb.human_corrected_status == "verdict_matched"
    assert fb.corrected_value == "ø30"
    assert fb.finding_snapshot["rev_text"] == "ø25"


def test_build_bundle_offline_from_fake_feedback():
    """The learned-model trainer's pure builder runs offline (no live DB)."""
    from types import SimpleNamespace
    from infrastructure.learning.trainer import build_bundle

    docs = [
        SimpleNamespace(
            human_corrected_status="dismissed", category="drawing_views", entity_text="LEGEND",
            original_status="CHANGED", corrected_category=None, corrected_value=None, created_at=None,
            finding_snapshot={"rev_text": "LEGEND", "ref_text": "LEGEND", "category": "drawing_views"},
        )
    ]
    bundle = build_bundle(docs)
    assert bundle["n_total"] == 1
    assert bundle["exact_matched"]  # the dismissal is remembered as an exact override
