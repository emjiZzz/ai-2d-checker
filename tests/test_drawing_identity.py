"""The reference/revision pair guard: does it actually discriminate, and does it fail open?

Two properties matter, and they are not symmetric:

  * A **false reject** deletes a drawing the user just uploaded. Absent or unrecognised
    evidence must therefore never reject.
  * A **false accept** only runs the comparison the user already asked for.

The discrimination numbers quoted in `drawing_identity.py` come from the eval corpus
(7/7 real pairs share a token, 42/42 cross-pairings share none). That corpus is gitignored,
so `test_corpus_pairs_are_discriminated` skips when it is absent rather than silently
passing — the fixtures below carry the same shapes and always run.
"""
import json
from pathlib import Path

import pytest

from services.backend.infrastructure.cad.drawing_identity import (
    extract_drawing_numbers,
    is_pair_mismatch,
)

CORPUS = Path(__file__).resolve().parent.parent / "storage" / "eval" / "pairs"


def text(value: str, layer: str = "RAHM2") -> dict:
    return {"entity_type": "text", "layer": layer, "properties": {"text": value}}


# --- extraction -------------------------------------------------------------------------


def test_extracts_the_drawing_number_from_a_standalone_token():
    """The number is its own text entity, NOT 'DWG NO: M745203N01'.

    This is exactly what `detect_revision` gets wrong — it requires label and value in one
    string, and this title block rules them into separate cells.
    """
    assert extract_drawing_numbers([text("M745203N01")]) == ["M745203N01"]


def test_extraction_does_not_depend_on_the_layer_name():
    """The measured layers are RAHM2 / WAKU / NoLayerName_001 — none of which contain
    'border' or 'title', which is `detect_revision`'s other broken gate."""
    for layer in ("RAHM2", "WAKU", "NoLayerName_001", "7A", "6"):
        assert extract_drawing_numbers([text("M7452A0N01", layer=layer)]) == ["M7452A0N01"]


def test_ignores_prose_and_dimensions():
    entities = [
        text("2 ロール：4 （2×2台）"),
        text("指示なき角部は糸面取りのこと"),
        text("6-6.6キリ11ザグリ深6.5"),
        text("22.70"),
        text("1:2.5"),
        text("2026/07/03"),
        text("FSRS2"),
    ]
    assert extract_drawing_numbers(entities) == []


def test_non_text_entities_are_never_scanned():
    """A layer record carries its name in `properties`; only text entities may contribute."""
    assert extract_drawing_numbers([
        {"entity_type": "layer", "layer": "M745203N01", "properties": {"color": 7}},
        {"entity_type": "line", "layer": "0", "properties": {"text": "M745203N01"}},
    ]) == []


def test_result_is_sorted_and_deduplicated():
    """Stored on the DrawingDocument and compared between drawings, so it must be stable
    across re-ingests rather than reflecting entity order."""
    entities = [text("M745227N01"), text("C2801P"), text("M745227N01")]
    assert extract_drawing_numbers(entities) == ["C2801P", "M745227N01"]


# --- the mismatch decision --------------------------------------------------------------


def test_same_number_on_both_sides_is_not_a_mismatch():
    assert is_pair_mismatch(["M7452A0N01"], ["M7452A0N01"]) is False


def test_different_numbers_are_a_mismatch():
    """The reported case: M745228N01 in one slot, M745219N01 in the other."""
    assert is_pair_mismatch(["M745228N01"], ["M745219N01"]) is True


def test_extra_noise_on_one_side_does_not_break_a_real_pair():
    """M745227N01's reference genuinely carries a stray `C2801P` alongside its number.

    The guard asks whether the sheets SHARE a number, never which token is the real one —
    this is the case that design choice exists for.
    """
    assert is_pair_mismatch(["C2801P", "M745227N01"], ["M745227N01"]) is False


@pytest.mark.parametrize(
    "ref, rev",
    [
        ([], ["M745203N01"]),
        (["M745203N01"], []),
        ([], []),
    ],
)
def test_absent_evidence_is_never_a_mismatch(ref, rev):
    """The load-bearing safety property. A sheet with unrecognised numbering, or a drawing
    ingested before this field existed, yields nothing — and must still be allowed through.
    Rejecting on no evidence would delete a good upload."""
    assert is_pair_mismatch(ref, rev) is False


def test_comparison_is_case_insensitive():
    assert is_pair_mismatch(["m745203n01"], ["M745203N01"]) is False


# --- against the real corpus ------------------------------------------------------------


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


@pytest.mark.skipif(not CORPUS.exists(), reason="eval corpus payloads are gitignored")
def test_corpus_pairs_are_discriminated():
    """Every real pair passes and every cross-pairing is rejected.

    This is the measurement the module's docstring quotes; pinned here so a change to the
    shape pattern cannot quietly break it.
    """
    sides: dict[str, dict[str, list[str]]] = {}
    for d in sorted(CORPUS.iterdir()):
        if not d.is_dir() or "-" in d.name:  # skip mutation pairs
            continue
        entry = {
            side: extract_drawing_numbers(_load(d / f"{side}.entities.jsonl"))
            for side in ("ref", "rev")
            if (d / f"{side}.entities.jsonl").exists()
        }
        if "ref" in entry and "rev" in entry:
            sides[d.name] = entry

    if not sides:
        pytest.skip("no corpus pairs present")

    for pair_id, e in sides.items():
        assert e["ref"] and e["rev"], f"{pair_id}: a side yielded no tokens at all"
        assert not is_pair_mismatch(e["ref"], e["rev"]), (
            f"{pair_id}: a REAL pair was rejected — this would delete a good upload"
        )

    for a in sides:
        for b in sides:
            if a == b:
                continue
            assert is_pair_mismatch(sides[a]["ref"], sides[b]["rev"]), (
                f"ref[{a}] x rev[{b}]: two unrelated drawings were accepted as a pair"
            )
