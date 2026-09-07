"""
Safe zones (tolerance, shim) keep their content-anchored detection over a template box.

A template box is fractions of render_bounds, so on a differently-shaped sheet it can land
away from the real table (the aspect caveat). For a COMPARED zone the user's pinned box should
win, but tolerance/shim are never compared — their box exists only to *exclude* printed
furniture. If a misplaced template box replaces the content-anchored tolerance box, the real
表示外公差 table stops being excluded and gets diffed as BOM. So for these zones a content-aware
detection outranks the template; the template only applies when detection missed.

extract_dynamic_regions (detection) and resolve_zone_overrides (template) are both mocked, so
this exercises only the override-application policy in extract_dynamic_regions_async.
"""
import pytest

import services.backend.infrastructure.audit.bom.table_extractor as te

pytestmark = pytest.mark.asyncio

DETECTED_TOLERANCE = (10.0, 10.0, 50.0, 50.0)     # where the anchor actually found the table
TEMPLATE_TOLERANCE = (500.0, 500.0, 540.0, 540.0)  # a misplaced pinned box, far away
RENDER_BOUNDS = [0.0, 0.0, 1000.0, 1000.0]


def _patch_detection(monkeypatch, confidence: str):
    """Make extract_dynamic_regions return a fixed detected tolerance box with `confidence`."""
    def fake_detection(entities):
        return {
            "tolerance": DETECTED_TOLERANCE,
            "_zone_confidence": {"tolerance": confidence},
        }
    monkeypatch.setattr(te, "extract_dynamic_regions", fake_detection)


def _patch_template(monkeypatch, box):
    async def fake_overrides(render_bounds, signature=None):
        return {"tolerance": box}
    monkeypatch.setattr(
        "services.backend.infrastructure.audit.bom.zone_template_resolver.resolve_zone_overrides",
        fake_overrides,
    )


async def test_content_anchored_tolerance_ignores_misplaced_template(monkeypatch):
    _patch_detection(monkeypatch, confidence="content_aware")
    _patch_template(monkeypatch, TEMPLATE_TOLERANCE)

    regions = await te.extract_dynamic_regions_async([], render_bounds=RENDER_BOUNDS)

    # The anchored detection wins — the misplaced template box is not applied.
    assert regions["tolerance"] == DETECTED_TOLERANCE
    assert regions["_zone_confidence"]["tolerance"] == "content_aware"


async def test_template_applies_when_detection_did_not_anchor(monkeypatch):
    # Detection fell back to the percentage grid (no anchor) — here the user's pin is a genuine
    # fallback and must be honoured, so the safe zone still has *some* box to exclude with.
    _patch_detection(monkeypatch, confidence="percentage_fallback")
    _patch_template(monkeypatch, TEMPLATE_TOLERANCE)

    regions = await te.extract_dynamic_regions_async([], render_bounds=RENDER_BOUNDS)

    assert regions["tolerance"] == TEMPLATE_TOLERANCE
    assert regions["_zone_confidence"]["tolerance"] == "user_pinned_template"
