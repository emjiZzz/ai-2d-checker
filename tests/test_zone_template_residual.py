"""Zones are an allowlist, and an allowlist needs a residual check.

`Gotcha - A Zone Template Gap Hid Half of a Real Change` recorded the transferable rule: a
hand-drawn zone set should be tested for gaps, not only for whether each box is in the right
place. This file is that check.

## Why it is content-based, and not a geometry adjacency assertion

The obvious implementation — assert no vertical gap between vertically adjacent boxes — was
written, measured against the live template, and rejected. On `aspect-1.414` there are five
stacked pairs whose gaps are all the same order of magnitude:

    bom              above views        0.0228  (~7.4 CAD)   <- the real defect
    title_upper_left above views        0.0241  (~7.9 CAD)
    views            above tolerance    0.0260  (~8.5 CAD)   <- ordinary sheet whitespace
    views            above title        0.0213  (~7.0 CAD)   <- ordinary sheet whitespace
    title_upper_left above notes        0.0136  (~4.5 CAD)

No threshold separates them, because size is not what makes a gap a defect: content sitting in
it is. The margin between the drawing area and the title block is supposed to be empty. A
geometry-only guard would fail on four harmless gaps, and a guard that cries wolf gets its
tolerance widened until it passes — which is how the original defect survived hand-alignment in
the first place.

So the invariant asserted here is the one that actually matters: no comparable row lands
outside every zone. It needs real pairs, and the eval payloads are gitignored, so it skips in
CI exactly like `test_eval_corpus.py::test_deterministic_candidates_run_offline_over_a_real_pair`.
That is a real limitation and is stated rather than papered over.
"""
import pytest

from services.backend.infrastructure.audit.bom.zone_template_resolver import (
    overrides_from_template_zones,
)
from services.backend.infrastructure.audit.comparison.spatial_differ import SpatialDiffer
from services.backend.infrastructure.eval.corpus import (
    CorpusPayloadMissingError,
    default_fixtures_dir,
    load_corpus,
)
from tools.eval_corpus import BUCKET_NO_ZONE, anchor_of, triage_row


def _inventory(entities, side):
    """`{normalised text -> [(address, entity)]}`, keyed exactly as the worksheet keys it.

    Uses the engine's own normaliser, which the annotation guideline requires: labels and
    inference must share one definition of "the same text".
    """
    buckets: dict[str, list] = {}
    for index, entity in enumerate(entities):
        display, key = SpatialDiffer._comparison_value(entity)
        if not display or not key:
            continue
        address = f"{side}-{entity.handle}" if entity.handle else f"{side}#{index}"
        buckets.setdefault(key, []).append((address, entity, display))
    return buckets


def _rows_in_no_zone(pair):
    """Unmatched rows that belong to no zone, as `(address, x, y, text)`.

    Unmatched only, and that scope is the point. A row present and identical on both sides
    cannot hide a change, so it costs nothing wherever it sits — and the sheet frame's grid
    labels (`Ａ`, `Ｂ`, `１`, `２`, …) sit outside every zone by design on every drawing here.
    Asserting over all rows flags ~60 of those per pair, and the guideline already excludes them
    under its own "sheet frame and grid labels" rule. Only a row that *differs* between the two
    sides can be the missing label this check exists to prevent.
    """
    ref_drawing, rev_drawing, ref_entities, rev_entities = pair.load()
    ref_index = _inventory(ref_entities, "REF")
    rev_index = _inventory(rev_entities, "REV")

    # Exactly the two key sets `cmd_worksheet` sends through `bucketed()`. Count deltas are
    # deliberately not included: the worksheet prints them in their own section without zone
    # triage, so the annotator is never told to skip one for being out of zone, and this check
    # asserts about what the annotator is actually told.
    unmatched = {
        "REF": [k for k in ref_index if k not in rev_index],
        "REV": [k for k in rev_index if k not in ref_index],
    }

    stranded = []
    for side, drawing, meta, index in (
        ("REF", ref_drawing, pair.ref, ref_index),
        ("REV", rev_drawing, pair.rev, rev_index),
    ):
        boxes = overrides_from_template_zones(
            meta.zone_template, (drawing.metadata or {}).get("render_bounds")
        )
        if not boxes:
            # No captured template is "unknown", not "no gaps" — `triage_row` sends every row to
            # review in that case, so there is nothing to assert and asserting zero would pass
            # vacuously. Skipped at the caller instead.
            return None
        for key in set(unmatched[side]):
            for address, entity, display in index.get(key, []):
                anchor = anchor_of(entity)
                if len(anchor) < 2:
                    continue
                if triage_row(boxes, anchor)[0] != BUCKET_NO_ZONE:
                    continue
                stranded.append((address, anchor[0], anchor[1], display[:40]))
    return stranded


# Rows accepted as genuinely out of zone, each with the reason it is not a template defect.
#
# An exemption is a claim that no *correct* box reaches this row, and it is deliberately keyed by
# `pair_id` + address rather than by a coordinate tolerance: a named row cannot quietly grow into
# a class. Anything not listed here still fails, which is the whole value of the check.
KNOWN_OUT_OF_ZONE = {
    # A lone fastener callout 6.6 units above `bom`'s top edge, at x=320.3 — far right of `notes`
    # (x 33.8-166.1) and above the drawn BOM table. Nothing else occupies that band on the
    # reference, and the revision's equivalent band holds only sheet grid labels, so there is no
    # zone this belongs to and no shape that would enclose it without misrepresenting the sheet.
    # Reviewed and accepted 2026-08-12 rather than zoned; see the gotcha note.
    ("M745203N01", "REF-192"),
}


def test_no_corpus_row_falls_outside_every_zone():
    """The residual check, stated as the annotator experiences it.

    A row here is not merely mis-filed — the annotation guideline instructs the checker to
    skip it and file a zone-detection bug, so it produces a *missing* label rather than a
    wrong one, and the engine misses it too. Precision and recall both stay clean while ground
    truth quietly loses a real change. That is the one failure mode this corpus cannot
    self-detect, which is why it is asserted rather than reported.
    """
    corpus = load_corpus(fixtures_dir=default_fixtures_dir(), allow_stale_guideline=True)
    if not corpus.pairs:
        pytest.skip("No pairs registered in the corpus manifest yet.")

    checked, failures, exempt_seen = 0, [], set()
    for pair in corpus.pairs:
        if pair.provenance != "human":
            continue
        try:
            stranded = _rows_in_no_zone(pair)
        except CorpusPayloadMissingError:
            continue
        if stranded is None:
            continue
        checked += 1
        for address, x, y, text in stranded:
            if (pair.pair_id, address) in KNOWN_OUT_OF_ZONE:
                exempt_seen.add((pair.pair_id, address))
                continue
            failures.append(f"{pair.pair_id} {address} @({x:.1f}, {y:.1f}) {text}")

    if not checked:
        pytest.skip("No human pair payloads on this machine (gitignored).")

    assert not failures, (
        f"{len(failures)} row(s) across {checked} pair(s) belong to no zone. Each is a row the "
        "guideline tells the annotator to skip, so it becomes a missing label the engine also "
        "misses. Fix the template, do not label around it:\n  " + "\n  ".join(failures)
    )

    # A stale exemption is the failure mode this check would otherwise acquire over time: once a
    # template repair or a re-export makes one unnecessary, leaving it listed silently re-opens a
    # hole for the next row that lands there.
    stale = KNOWN_OUT_OF_ZONE - exempt_seen
    assert not stale, (
        f"{len(stale)} exemption(s) in KNOWN_OUT_OF_ZONE no longer match any stranded row and "
        f"must be deleted: {sorted(stale)}"
    )
