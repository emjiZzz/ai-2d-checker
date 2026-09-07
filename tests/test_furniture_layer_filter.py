"""Regression: the drawing_views furniture filter must recognize the romanized frame layer.

KMTI AutoCAD sheets put all sheet furniture — title block, the 表示外公差 tolerance table, BOM
labels — on a layer named "WAKU" (the romanization of 枠, "frame/border"). The furniture filter
historically checked only the kanji 枠, so on these sheets it never matched: furniture cells such
as "2589" (previous dwg. no.) and "2.5" (a tolerance grade) sit BELOW the content-anchored
tolerance box, survive views-scoping, and get diffed as drawing_views — producing false
MISMATCHED markings on the tolerance table and title block. See the Gotcha vault note.

Real drawing content on these sheets lives on numbered layers (2, 5, 6, 7A, 8) and must NOT be
filtered — that would drop genuine findings.
"""
from services.backend.infrastructure.audit.comparison.orchestrator import is_furniture_layer


def test_romanized_waku_frame_layer_is_furniture():
    assert is_furniture_layer("WAKU") is True
    assert is_furniture_layer("waku") is True
    assert is_furniture_layer("WAKU-DIM") is True  # substring match tolerates suffixes


def test_kanji_and_tolerance_layers_still_match():
    # The pre-existing tokens must keep working.
    assert is_furniture_layer("枠") is True
    assert is_furniture_layer("公差") is True
    assert is_furniture_layer("TOLERANCE") is True
    assert is_furniture_layer("Tol_Table") is True


def test_real_drawing_layers_are_not_furniture():
    # Numbered / geometry layers carry real drawing content — never filter them.
    for lyr in ("2", "5", "6", "7A", "8", "RAHM2", "0", "NoLayerName_001"):
        assert is_furniture_layer(lyr) is False, lyr


def test_empty_or_none_layer_is_not_furniture():
    assert is_furniture_layer("") is False
    assert is_furniture_layer(None) is False
