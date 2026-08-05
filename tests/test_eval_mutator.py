"""Stage 0c — the mutation generator.

Mutation pairs are the only ground truth this project can produce without an annotator, so
the generator's own correctness is load-bearing: a mutator bug does not show up as a broken
test somewhere, it shows up as a permanently wrong precision or recall number that nobody
can trace back.

Two classes of test here, and the second is the one that caught real bugs:

  * **Determinism and addressing** — same seed, same bytes; addresses survive a deletion
    shifting every later index.
  * **The zero-finding operators** — `null_mutation`, `restyle_dimension_text` and
    `translate_entities` must change the drawing (or not) in ways the annotation guideline
    says are *not* findings. If one of them ever starts emitting a finding, the corpus
    quietly stops measuring precision.

See `docs/vault/00 - AI Maturity Status.md` and CLAUDE.md constraint 5.
"""

import pytest

from services.backend.infrastructure.eval.corpus import VALID_CATEGORIES, VALID_STATUSES
from services.backend.infrastructure.eval.mutator import (
    ZERO_FINDING_OPERATORS,
    Mutator,
    _retarget_number,
)
from services.backend.infrastructure.eval.serialize import EvalDrawing, EvalEntity


def _text(handle, value, x, y, layer="0"):
    return EvalEntity(
        entity_type="text",
        layer=layer,
        handle=handle,
        properties={"text": value, "handle": handle},
        geometry={"insert": [float(x), float(y)]},
    )


def _dimension(handle, text, measurement, x, y):
    return EvalEntity(
        entity_type="dimension",
        layer="DIM",
        handle=handle,
        properties={"text": text, "measurement": measurement, "dim_type": 3, "handle": handle},
        geometry={"text_point": [float(x), float(y)], "def_point": [float(x), float(y) + 40.0]},
    )


def _line(handle, x0, y0, x1, y1):
    return EvalEntity(
        entity_type="line",
        layer="FRAME",
        handle=handle,
        properties={"handle": handle},
        geometry={"start": [float(x0), float(y0)], "end": [float(x1), float(y1)]},
    )


@pytest.fixture
def base():
    """A synthetic sheet wide enough that the percentage-fallback zone grid is usable.

    Deliberately synthetic rather than loaded from the corpus: the real payloads are
    gitignored, and a test that skips in CI is not a guard.

    The frame lines are not decoration. `compute_drawing_bounds` derives the sheet extent
    from `line`/`polyline` geometry only, so a text-only fixture yields no bounds, every
    zone collapses to the same default box — including `tolerance`, a safe zone — and the
    mutator correctly finds that every entity is inside a safe zone and refuses to touch
    anything. A drawing without a frame is not a drawing.
    """
    entities = [
        _line("F01", 0, 0, 1000, 0),
        _line("F02", 1000, 0, 1000, 900),
        _line("F03", 1000, 900, 0, 900),
        _line("F04", 0, 900, 0, 0),
    ]
    entities += [
        _text(f"T{i:02X}", f"note {i} value {100 + i}", 80 + (i % 5) * 60, 300 + (i // 5) * 40)
        for i in range(20)
    ]
    entities += [
        _dimension("D01", "%%c120", 120.0, 420.0, 500.0),
        _dimension("D02", "45", 45.0, 500.0, 520.0),
    ]
    drawing = EvalDrawing(
        id="base0001",
        file_name="base.dxf",
        file_hash="f" * 64,
        metadata={"render_bounds": [0.0, 0.0, 1000.0, 900.0]},
    )
    return Mutator(drawing, entities, {"TITLE": "FSRS2", "DWG_NO": "M745200N01"})


# ─── determinism ──────────────────────────────────────────────────────────────────────


def test_same_seed_reproduces_the_pair_exactly(base):
    """The manifest records a seed instead of the generated labels, so reproduction has to
    be exact — otherwise the committed recipe and the untracked labels disagree."""
    first = base.generate("P", seed=7)
    second = base.generate("P", seed=7)

    assert [e.to_dict() for e in first.entities] == [e.to_dict() for e in second.entities]
    assert [f.to_dict() for f in first.findings] == [f.to_dict() for f in second.findings]
    assert first.applied == second.applied
    assert first.drawing.id == second.drawing.id


def test_mutated_side_gets_its_own_drawing_identity(base):
    """It must resolve its *own* title-block OCR cache entry. Sharing the base's would let
    a cached OCR value win over the spatial reading and mask a title mutation."""
    pair = base.generate("P", seed=7)
    assert pair.drawing.id != base.base_drawing.id
    assert pair.drawing.file_hash != base.base_drawing.file_hash


def test_base_entities_are_never_mutated(base):
    """Every pair shares one base; an in-place edit would leak into the next pair."""
    before = [e.to_dict() for e in base.base_entities]
    for seed in range(5):
        base.generate(f"P{seed}", seed=seed)
    assert [e.to_dict() for e in base.base_entities] == before


# ─── the zero-finding operators ───────────────────────────────────────────────────────


def test_null_mutation_changes_nothing_and_expects_nothing(base):
    pair = base.generate("N", seed=1, operators=["null_mutation"])
    assert pair.findings == []
    assert pair.is_null_pair
    assert [e.to_dict() for e in pair.entities] == [e.to_dict() for e in base.base_entities], (
        "A null pair's two sides must be byte-identical — that is the entire basis for "
        "reading every finding an engine reports on it as a false positive."
    )


def test_restyle_dimension_text_moves_display_text_but_not_the_measurement(base):
    """`%%c120` and a style default both render ⌀120; the guideline calls that a
    transcoding, and the differ keys on `measurement` for exactly that reason."""
    pair = base.generate("R", seed=3, operators=["restyle_dimension_text"])
    assert pair.findings == []

    before = {e.handle: e for e in base.base_entities if e.entity_type == "dimension"}
    after = {e.handle: e for e in pair.entities if e.entity_type == "dimension"}
    changed = [h for h in before if after[h].properties["text"] != before[h].properties["text"]]
    assert changed, "the operator reported success but no dimension text moved"
    for handle in changed:
        assert after[handle].properties["measurement"] == before[handle].properties["measurement"]


def test_translate_entities_moves_geometry_but_not_text(base):
    """Pure relocation with identical text is not a finding, per the guideline."""
    pair = base.generate("M", seed=5, operators=["translate_entities"])
    assert pair.findings == []

    before = {e.handle: e for e in base.base_entities if e.handle}
    moved = 0
    for entity in pair.entities:
        original = before.get(entity.handle)
        if original is None:
            continue
        assert entity.properties.get("text") == original.properties.get("text")
        if entity.geometry.get("insert") != original.geometry.get("insert"):
            moved += 1
    assert moved, "the operator reported success but nothing moved"


def test_every_zero_finding_operator_is_declared():
    """The scorer reports these separately — they measure precision only, and folding them
    into a recall denominator divides by zero."""
    assert ZERO_FINDING_OPERATORS == {
        "null_mutation",
        "restyle_dimension_text",
        "translate_entities",
    }


# ─── addressing ───────────────────────────────────────────────────────────────────────


def test_addresses_survive_a_deletion_shifting_later_indices(base):
    """A payload address is a line number, and `delete_text` renumbers everything after it.

    Addresses are therefore resolved once, against the final entity list, rather than
    recorded as the mutation is applied.
    """
    pair = base.generate("D", seed=11, operators=["delete_text", "edit_text", "delete_text"])
    assert pair.findings, "no mutation applied; the fixture offers no eligible target"

    for finding in pair.findings:
        side, kind, value = finding.address
        entities = base.base_entities if side == "REF" else pair.entities
        if kind == "payload_index":
            assert 0 <= int(value) < len(entities), (
                f"{finding.qualified_handle} points past the end of the {side} payload — "
                f"an index recorded before the deletions were applied."
            )
        resolved = finding.resolve(base.base_entities, pair.entities)
        assert resolved is not None, f"{finding.qualified_handle} resolves to nothing"


def test_removed_findings_anchor_on_the_reference_side(base):
    pair = base.generate("D", seed=11, operators=["delete_text", "delete_text"])
    removed = [f for f in pair.findings if f.status == "REMOVED"]
    assert removed, "no deletion applied"
    for finding in removed:
        assert finding.address[0] == "REF", (
            "A REMOVED entity does not exist on the revision side, so its address cannot "
            "be there either."
        )


def test_generated_findings_are_schema_valid(base):
    """Generated labels go through the same validation as hand-written ones — an operator
    that invents a category must fail here, not in a sweep six weeks later."""
    for seed in range(12):
        for finding in base.generate(f"P{seed}", seed=seed).findings:
            assert finding.category in VALID_CATEGORIES
            assert finding.status in VALID_STATUSES
            assert finding.entity_handle.strip()


# ─── targeting ────────────────────────────────────────────────────────────────────────


def test_targets_never_include_safe_zone_content(base):
    """`tolerance` and the shim table are never compared, so an edit inside one has ground
    truth 'no finding' — a different probe from these operators, and mixing it in would
    inflate their false-positive counts."""
    for zone in ("views", "notes", "bom", "iso", "title"):
        for entity in base.candidates(base.base_entities, zone):
            assert not base._in_safe_zone(entity)


def test_targets_are_restricted_to_comparable_entity_types(base):
    """The differ compares text and dimensions only. Mutating a line produces a label no
    engine can satisfy — which reads as a recall miss that is really a mutator bug."""
    assert base.candidates(base.base_entities, "views", entity_type="line") == []


def test_dimension_text_and_measurement_stay_coherent(base):
    """They were bumped by two independent random draws, producing a dimension whose text
    said 125 while its measurement said 119 — and a label whose `rev_text` contradicted the
    value the differ actually compares."""
    pair = base.generate("X", seed=2, operators=["edit_dimension_measurement"])
    assert pair.findings, "no dimension mutated"
    for entity in pair.entities:
        if entity.entity_type != "dimension":
            continue
        text = str(entity.properties.get("text") or "")
        measurement = entity.properties.get("measurement")
        if not text or measurement is None or text.strip() == "":
            continue
        digits = "".join(c for c in text if c.isdigit() or c == ".")
        assert digits.startswith(f"{float(measurement):g}".split(".")[0]), (
            f"dimension text {text!r} disagrees with measurement {measurement}"
        )


@pytest.mark.parametrize(
    ("text", "value", "expected"),
    [
        ("%%c120", 125.0, "%%c125"),
        ("22.7", 24.0, "24"),
        ("22.7", 22.75, "22.75"),
        ("R5", 7.5, "R7.5"),
        ("no digits", 12.0, "12"),
    ],
)
def test_retarget_number_keeps_the_callout_shape(text, value, expected):
    assert _retarget_number(text, value) == expected
