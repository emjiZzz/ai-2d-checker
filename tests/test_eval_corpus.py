"""Stage 0b — the evaluation corpus.

Three rules from the annotation guideline are enforced in code rather than by discipline,
because each of them fails silently: payload drift, held-out discipline, and guideline
versioning. Those enforcements are what these tests pin. If any of them can be bypassed,
every metric the ladder ever produces is unfalsifiable.

The last test in the file is the one that matters most: it runs the real
`generate_deterministic_candidates` over a real exported pair, offline, and is the first
thing in this repository to demonstrate that the eval seam actually exists rather than
being asserted to exist in a plan. It skips when the gitignored payloads are absent.

See `docs/vault/00 - AI Maturity Status.md` and CLAUDE.md constraint 5.
"""

import json

import pytest

from services.backend.infrastructure.audit.comparison.cache_manager import (
    ComparisonCacheManager,
)
from services.backend.infrastructure.audit.comparison.taxonomy import TAXONOMY
from services.backend.infrastructure.eval.corpus import (
    GUIDELINE_VERSION,
    MANIFEST_SCHEMA_VERSION,
    VALID_CATEGORIES,
    CorpusDriftError,
    CorpusPayloadMissingError,
    ExpectedFinding,
    HeldOutAccessError,
    LabelSchemaError,
    PairLabels,
    PairSide,
    default_fixtures_dir,
    empty_manifest,
    held_out_access_log,
    load_corpus,
    read_manifest,
    write_manifest,
)
from services.backend.infrastructure.eval.serialize import (
    EvalDrawing,
    EvalEntity,
    canonical_json,
    entities_from_jsonl,
    entities_to_jsonl,
    read_text_stable,
    write_text_stable,
)

# ─── fixtures ─────────────────────────────────────────────────────────────────────────


def _entity(handle=None, text="", layer="0", x=0.0, y=0.0, entity_type="text"):
    return EvalEntity(
        entity_type=entity_type,
        layer=layer,
        handle=handle,
        properties={"text": text, "handle": handle},
        geometry={"insert": [x, y]},
    )


@pytest.fixture
def corpus_root(tmp_path, monkeypatch):
    """A two-pair corpus on disk, one of them held out."""
    fixtures = tmp_path / "fixtures"
    payloads = tmp_path / "payloads"
    monkeypatch.setenv("EVAL_CORPUS_FIXTURES", str(fixtures))
    monkeypatch.setenv("EVAL_CORPUS_PAYLOADS", str(payloads))

    manifest = empty_manifest()
    for pair_id, held_out in (("OPEN01", False), ("HELD01", True)):
        sides = {}
        for side in ("ref", "rev"):
            drawing = EvalDrawing(
                id=f"{pair_id}{side}", file_name=f"{pair_id}_{side}.dxf", file_hash="h" * 64
            )
            entities = [
                _entity(handle="1A", text="ø120", x=10, y=10),
                _entity(handle=None, text="注記" if side == "ref" else "注記2", x=20, y=20),
            ]
            drawing_sha = write_text_stable(
                payloads / pair_id / f"{side}.drawing.json", canonical_json(drawing.to_dict())
            )
            entities_sha = write_text_stable(
                payloads / pair_id / f"{side}.entities.jsonl", entities_to_jsonl(entities)
            )
            sides[side] = PairSide(
                drawing_id=drawing.id,
                file_name=drawing.file_name,
                file_hash=drawing.file_hash,
                drawing_sha256=drawing_sha,
                entities_sha256=entities_sha,
                entity_count=len(entities),
            ).to_dict()
        manifest["pairs"].append(
            {
                "pair_id": pair_id,
                "provenance": "human",
                "held_out": held_out,
                "label_state": "unlabelled",
                "labels": None,
                "notes": "",
                **sides,
            }
        )
    write_manifest(manifest, fixtures)
    return fixtures, payloads


# ─── payload integrity: a silently edited fixture invalidates every historical number ──


def test_drifted_payload_fails_loudly(corpus_root):
    _, payloads = corpus_root
    target = payloads / "OPEN01" / "rev.entities.jsonl"
    write_text_stable(target, read_text_stable(target).replace("注記2", "注記3"))

    corpus = load_corpus()
    with pytest.raises(CorpusDriftError) as exc:
        corpus.verify_all()
    message = str(exc.value)
    assert "OPEN01/rev" in message
    assert "do not update the manifest to match" in message, (
        "The drift message must say what to do. 'Update the manifest' is the tempting fix "
        "and the wrong one — it retroactively relabels every number ever measured."
    )


def test_missing_payload_is_distinguished_from_drift(corpus_root):
    """A fresh clone has the manifest and no payloads. That is expected, not corruption."""
    _, payloads = corpus_root
    (payloads / "OPEN01" / "ref.entities.jsonl").unlink()

    corpus = load_corpus()
    with pytest.raises(CorpusPayloadMissingError):
        corpus.verify_all()


def test_intact_corpus_verifies(corpus_root):
    load_corpus().verify_all()


# ─── held-out discipline ──────────────────────────────────────────────────────────────


def test_held_out_pairs_are_excluded_by_default(corpus_root):
    ids = {pair.pair_id for pair in load_corpus()}
    assert ids == {"OPEN01"}, (
        "Held-out pairs must not be reachable by an ordinary load. A sweep that can see "
        "them will fit to them and report an F1 that does not exist."
    )


def test_including_held_out_pairs_requires_a_reason(corpus_root):
    with pytest.raises(HeldOutAccessError):
        load_corpus(include_held_out=True)


def test_held_out_access_is_logged(corpus_root):
    corpus = load_corpus(include_held_out=True, held_out_reason="stage 0.5 final validation")
    assert {pair.pair_id for pair in corpus} == {"OPEN01", "HELD01"}

    entries = read_text_stable(held_out_access_log()).splitlines()
    assert len(entries) == 1
    assert "HELD01" in entries[0]
    assert "stage 0.5 final validation" in entries[0]


def test_status_report_counts_held_out_pairs_even_when_excluded(corpus_root):
    report = load_corpus().status_report()
    assert report["held_out"] == 1
    assert report["human_pairs"] == 2, (
        "The report reads the manifest, not the loaded subset — otherwise excluding the "
        "held-out pairs would make the corpus look smaller than it is."
    )
    assert report["stage_0b_complete"] is False


# ─── label schema ─────────────────────────────────────────────────────────────────────


def test_categories_come_from_the_taxonomy_not_from_a_second_list():
    assert VALID_CATEGORIES == frozenset(TAXONOMY.keys()), (
        "A label category list maintained separately from taxonomy.py would drift, and a "
        "corpus labelled against a stale category set silently mis-scores attribution."
    )


def test_invented_category_is_rejected():
    with pytest.raises(LabelSchemaError):
        ExpectedFinding(entity_handle="REV-1A", category="dimensions", status="CHANGED")


def test_invalid_status_is_rejected():
    with pytest.raises(LabelSchemaError):
        ExpectedFinding(entity_handle="REV-1A", category="notes_section", status="MOVED")


def test_empty_address_is_rejected():
    with pytest.raises(LabelSchemaError):
        ExpectedFinding(entity_handle="  ", category="notes_section", status="CHANGED")


def test_stale_guideline_version_is_rejected():
    raw = {
        "pair_id": "OPEN01",
        "guideline_version": "2020-01-01",
        "annotator": "someone",
        "annotated_at": "2020-01-01",
        "findings": [],
    }
    with pytest.raises(LabelSchemaError) as exc:
        PairLabels.from_dict(raw)
    assert "re-label every affected pair or discard them" in str(exc.value)

    # Explicitly opting in is allowed — a migration needs to read the old labels first.
    assert PairLabels.from_dict(raw, allow_stale_guideline=True).pair_id == "OPEN01"


# ─── addressing: DXF handles are unavailable for block-exploded entities ──────────────


@pytest.mark.parametrize(
    ("raw", "status", "expected"),
    [
        ("REV-1B2A", "CHANGED", ("REV", "handle", "1B2A")),
        ("REF-1B2A", "REMOVED", ("REF", "handle", "1B2A")),
        ("REV#412", "ADDED", ("REV", "payload_index", "412")),
        ("REF#0", "REMOVED", ("REF", "payload_index", "0")),
        # Unprefixed: the revision side, except a REMOVED which can only be on the
        # reference side. Straight from the annotation guideline.
        ("1B2A", "CHANGED", ("REV", "handle", "1B2A")),
        ("1B2A", "REMOVED", ("REF", "handle", "1B2A")),
    ],
)
def test_address_parsing(raw, status, expected):
    finding = ExpectedFinding(entity_handle=raw, category="notes_section", status=status)
    assert finding.address == expected


def test_malformed_payload_address_is_rejected():
    with pytest.raises(LabelSchemaError):
        ExpectedFinding(entity_handle="REV#abc", category="notes_section", status="ADDED")


def test_both_address_forms_resolve_to_the_right_entity():
    ref = [_entity(handle="AA", text="ref-0"), _entity(handle=None, text="ref-1")]
    rev = [_entity(handle="BB", text="rev-0"), _entity(handle=None, text="rev-1")]

    by_handle = ExpectedFinding(
        entity_handle="REV-BB", category="notes_section", status="CHANGED"
    )
    by_index = ExpectedFinding(
        entity_handle="REF#1", category="notes_section", status="REMOVED"
    )
    assert by_handle.resolve(ref, rev).properties["text"] == "rev-0"
    assert by_index.resolve(ref, rev).properties["text"] == "ref-1"

    # An address that points nowhere is a corpus defect, reported as None rather than
    # silently matching the first entity.
    out_of_range = ExpectedFinding(
        entity_handle="REV#99", category="notes_section", status="ADDED"
    )
    assert out_of_range.resolve(ref, rev) is None


def test_handle_coverage_is_reported_not_assumed():
    labels = PairLabels(
        pair_id="X",
        guideline_version=GUIDELINE_VERSION,
        annotator="t",
        annotated_at="2026-08-05",
        findings=[
            ExpectedFinding("REV-1A", "notes_section", "CHANGED"),
            ExpectedFinding("REV#7", "notes_section", "ADDED"),
            ExpectedFinding("REF#9", "notes_section", "REMOVED"),
        ],
    )
    assert labels.handle_anchored_count == 1, (
        "The Stage 0d scorer is handle-first; this count is the fraction of the corpus on "
        "which handle-first matching actually applies."
    )
    assert labels.category_counts["notes_section"] == 3


# ─── serialization: byte stability is what makes the sha256 check meaningful ──────────


def test_entity_round_trip_is_lossless_and_stable():
    entities = [
        _entity(handle="1A", text="ø120 ±0.02", layer="WAKU", x=1.5, y=2.5),
        _entity(handle=None, text="素材調質施工　硬度HS35～38度", layer="6"),
    ]
    once = entities_to_jsonl(entities)
    twice = entities_to_jsonl(entities_from_jsonl(once))
    assert once == twice, "A round trip that is not byte-identical breaks every digest."

    restored = entities_from_jsonl(once)
    assert restored[1].properties["text"] == "素材調質施工　硬度HS35～38度"
    assert restored[0].geometry["insert"] == [1.5, 2.5]


def test_payloads_are_written_with_lf_endings(tmp_path):
    """Windows is the primary dev platform here; default text mode would emit CRLF and
    the same data would hash differently than it does in CI."""
    path = tmp_path / "p.jsonl"
    digest = write_text_stable(path, entities_to_jsonl([_entity(handle="1A", text="x")]))
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    assert digest == write_text_stable(path, read_text_stable(path))


def test_entity_exposes_exactly_the_attributes_the_differ_reads():
    """The load-bearing claim behind the whole offline harness.

    `generate_deterministic_candidates` reads these five off every entity and nothing
    else, which is why a duck-typed stub can stand in for a Beanie Document.
    """
    entity = _entity(handle="1A", text="x")
    for attribute in ("entity_type", "layer", "handle", "properties", "geometry"):
        assert hasattr(entity, attribute)
    # 71 call sites do `e.properties.get(...)` with no None guard.
    blank = EvalEntity(entity_type="line")
    assert blank.properties == {} and blank.geometry == {}


def test_handle_is_recovered_from_properties_when_the_column_is_null():
    """A Mongo row has `handle` present with value None while `properties.handle` is set.

    `setdefault` does not fire on a present-but-None key, so the promoted column has to be
    tested for truthiness rather than for presence.
    """
    entity = EvalEntity.from_document(
        {"entity_type": "text", "handle": None, "properties": {"handle": "2BA", "text": "x"}}
    )
    assert entity.handle == "2BA"


def test_drawing_id_survives_serialization():
    """The title-block OCR cache is keyed on `(drawing_id, file_hash)`. A synthetic id
    would miss that cache and turn an offline run into a live Gemini call."""
    drawing = EvalDrawing(id="6a712713da6a81f370c325a4", file_name="a.dxf", file_hash="abc")
    restored = EvalDrawing.from_dict(json.loads(canonical_json(drawing.to_dict())))
    assert restored.id == "6a712713da6a81f370c325a4"


def _ocr_pair(tmp_path, sha=""):
    from services.backend.infrastructure.eval.corpus import CorpusPair

    def side():
        return PairSide(
            drawing_id="D1",
            file_name="a.dxf",
            file_hash="H1",
            drawing_sha256="",
            entities_sha256="",
            entity_count=0,
            ocr_sha256=sha,
        )

    return CorpusPair(
        pair_id="P",
        provenance="human",
        held_out=False,
        label_state="unlabelled",
        ref=side(),
        rev=side(),
        payload_dir=tmp_path,
    )


def test_captured_ocr_is_restored_into_an_empty_cache(tmp_path):
    """The defect this closes: the title-block reading lived only in `storage/cache/`,
    outside the sha256-pinned corpus. Deleting old comparisons wiped it, and the engine
    silently fell back to spatial title extraction on one side while the other still had a
    reading — a different measurement, with no error and no changed byte in the corpus."""
    reading = '{"TITLE": "FSRS2", "DWG_NO": "M7452A0N01"}\n'
    sha = write_text_stable(tmp_path / "P" / "ref.ocr.json", reading)
    write_text_stable(tmp_path / "P" / "rev.ocr.json", reading)
    pair = _ocr_pair(tmp_path, sha)

    cache = tmp_path / "cache"
    cache.mkdir()
    assert pair.restore_ocr_cache(cache_dir=cache)
    assert (cache / pair.ref.ocr_cache_filename()).exists()
    assert read_text_stable(cache / pair.ref.ocr_cache_filename()) == reading

    # Idempotent: a second run restores nothing because nothing is missing.
    assert pair.restore_ocr_cache(cache_dir=cache) == []


def test_a_stale_cache_entry_is_replaced_not_deferred_to(tmp_path):
    """Restoring filled a GAP but could not repair a STALE entry, while its own docstring
    claimed it made a score reproducible and `run_corpus` claimed it made the score "a
    function of the corpus alone". Both were false whenever `storage/cache/` already held a
    different reading for the same drawing and file hash — the normal state on any machine
    that has run a live comparison, because the engine writes that cache itself.

    Measured on M745227N01 before the fix: planting a `STALE9999` DWG_NO and restoring
    reported "nothing restored" and left the planted value in place, so the run scored
    against a reading the corpus could not reproduce.
    """
    reading = '{"TITLE": "FSRS2", "DWG_NO": "M7452A0N01"}\n'
    sha = write_text_stable(tmp_path / "P" / "ref.ocr.json", reading)
    write_text_stable(tmp_path / "P" / "rev.ocr.json", reading)
    pair = _ocr_pair(tmp_path, sha)

    cache = tmp_path / "cache"
    cache.mkdir()
    target = cache / pair.ref.ocr_cache_filename()
    # What a live comparison leaves behind: same key, different reading.
    write_text_stable(target, '{"TITLE": "FSRS2", "DWG_NO": "STALE9999"}\n')

    reported = pair.restore_ocr_cache(cache_dir=cache)

    assert read_text_stable(target) == reading, (
        "the corpus is the authority for a reproducible score; a differing cache entry "
        "must lose, or the run scores against something the corpus cannot reproduce"
    )
    assert any("replaced" in name for name in reported), (
        "an overwrite must be reported distinctly from filling a gap -- silently repairing "
        "it trades one invisible state dependency for another"
    )


def test_a_reformatted_cache_entry_is_not_treated_as_stale(tmp_path):
    """The other half, and the reason this compares readings rather than bytes.

    **19 corpus pair-sides share one OCR cache key**: every mutation pair derives from a base
    drawing and reuses its id and file hash, so `M7452A0N01/ref` and 18 mutation sides all map
    to the same file. Their captured payloads were exported at different times and differ in
    JSON formatting alone -- measured 2026-08-17, every such collision in the corpus is
    identical after parse. A byte comparison calls all of them stale and rewrites them on every
    run: 4 writes per run, reported as if the corpus were drifting.
    """
    reading = '{"TITLE": "FSRS2", "DWG_NO": "M7452A0N01"}\n'
    sha = write_text_stable(tmp_path / "P" / "ref.ocr.json", reading)
    write_text_stable(tmp_path / "P" / "rev.ocr.json", reading)
    pair = _ocr_pair(tmp_path, sha)

    cache = tmp_path / "cache"
    cache.mkdir()
    target = cache / pair.ref.ocr_cache_filename()
    # Same reading, exported with different whitespace and key order.
    write_text_stable(target, '{\n  "DWG_NO":  "M7452A0N01",\n  "TITLE": "FSRS2"\n}\n')
    before = read_text_stable(target)

    reported = pair.restore_ocr_cache(cache_dir=cache)

    assert not any("replaced" in name for name in reported), (
        "a formatting-only difference is the same reading; reporting it as stale is noise "
        "that hides a real one"
    )
    assert read_text_stable(target) == before, "and it must not be rewritten either"


def test_drifted_ocr_capture_fails_loudly(tmp_path):
    sha = write_text_stable(tmp_path / "P" / "ref.ocr.json", '{"TITLE": "one"}\n')
    pair = _ocr_pair(tmp_path, sha)
    write_text_stable(tmp_path / "P" / "ref.ocr.json", '{"TITLE": "two"}\n')

    with pytest.raises(CorpusDriftError):
        pair.restore_ocr_cache(cache_dir=tmp_path / "cache")


def test_a_captured_reading_counts_as_offline_ready(tmp_path):
    """`missing_ocr_cache` asks "would this run differently?", not "is the cache warm?" —
    the runner restores captured readings before the run."""
    pair = _ocr_pair(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    assert len(pair.missing_ocr_cache(cache_dir=cache)) == 2

    write_text_stable(tmp_path / "P" / "ref.ocr.json", "{}\n")
    write_text_stable(tmp_path / "P" / "rev.ocr.json", "{}\n")
    assert pair.missing_ocr_cache(cache_dir=cache) == []


def test_uncaptured_sides_are_reported(tmp_path):
    """A pair still borrowing from the cache is one deletion away from scoring differently.
    Reported so the exposure is visible rather than discovered."""
    pair = _ocr_pair(tmp_path)
    assert pair.uncaptured_ocr_sides() == ["ref", "rev"]

    write_text_stable(tmp_path / "P" / "ref.ocr.json", "{}\n")
    assert pair.uncaptured_ocr_sides() == ["rev"]


#: Pairs known to be missing their captured title-block OCR reading, with why.
#:
#: `M745204N01` was exported when `storage/cache/` held no reading for either side, and none is
#: recoverable now — `_find_ocr_reading` misses by drawing id and by file hash. Capturing it means
#: running a comparison to MAKE the reading, which is a live Gemini call per side, so it is an
#: owner's decision rather than something a test run can fix. Owner's call 2026-08-25: leave it,
#: capture it by hand later.
#:
#: 🔴 **This is a real exposure, not a formality.** `generate_deterministic_candidates` calls
#: Gemini on a title-block OCR cache miss, so an eval run over this pair breaks the "zero network
#: calls" exit criterion and scores its title-block findings differently offline than in the app.
#:
#: ⚠ Empty this set the moment the reading is captured. The `xfail` below is **strict**, so the
#: suite fails on the day it starts passing — which is the reminder, and is deliberate: a standing
#: allowlist is a place for new breakage to hide.
KNOWN_UNCAPTURED_OCR = {"M745204N01"}


def _pairs_missing_ocr() -> dict[str, list[str]]:
    corpus = load_corpus(fixtures_dir=default_fixtures_dir())
    return {
        p.pair_id: p.uncaptured_ocr_sides()
        for p in corpus.pairs
        if p.uncaptured_ocr_sides()
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "M745204N01 has no OCR reading in storage/cache/ to capture; making one is a live "
        "Gemini call. Owner's call 2026-08-25. Remove this marker and the entry in "
        "KNOWN_UNCAPTURED_OCR once it is captured."
    ),
)
def test_committed_corpus_has_every_ocr_reading_captured():
    """Guards the real corpus, not a fixture. If a future export forgets to capture the
    reading, the corpus silently goes back to depending on a volatile cache."""
    exposed = _pairs_missing_ocr()
    assert not exposed, (
        f"{len(exposed)} pair(s) still borrow their title-block reading from "
        f"storage/cache/ instead of owning it: {sorted(exposed)[:5]}"
    )


def test_no_pair_beyond_the_known_one_is_missing_its_ocr_reading():
    """The guard the `xfail` above would otherwise switch off for the whole corpus.

    ⚠ **An `xfail` on a test that checks EVERY pair excuses every pair.** That is the trap: with
    only the marker above, a sixth pair exported tomorrow without its reading would be absorbed
    into the same expected failure and never reported. This asserts the exposure has not grown,
    so the known gap stays named and a new one still fails.
    """
    exposed = set(_pairs_missing_ocr())
    unexpected = exposed - KNOWN_UNCAPTURED_OCR
    assert not unexpected, (
        f"{len(unexpected)} pair(s) newly borrow their title-block reading from storage/cache/: "
        f"{sorted(unexpected)}. An eval run over these makes a live Gemini call."
    )


def test_zone_template_risk_is_reported_per_sheet_signature():
    """A pair whose sheet has a hand-aligned zone template is compared against different
    zone boxes offline than in the app — `resolve_zone_overrides` needs a Beanie session
    and `table_extractor` degrades to plain detection when it raises."""

    def side(signature):
        return PairSide(
            drawing_id="D",
            file_name="a.dxf",
            file_hash="H",
            drawing_sha256="",
            entities_sha256="",
            entity_count=0,
            zone_signature=signature,
        )

    from services.backend.infrastructure.eval.corpus import CorpusPair

    pair = CorpusPair(
        pair_id="P",
        provenance="human",
        held_out=False,
        label_state="unlabelled",
        ref=side("aspect-1.384"),
        rev=side("aspect-1.414"),
    )
    assert pair.zone_template_risk() == ["aspect-1.384", "aspect-1.414"]

    unknown = CorpusPair(
        pair_id="P",
        provenance="human",
        held_out=False,
        label_state="unlabelled",
        ref=side(""),
        rev=side(""),
    )
    assert unknown.zone_template_risk() == []


def test_ocr_cache_filename_matches_the_cache_managers_own_format():
    """Pins the offline-readiness check to the real cache key.

    `generate_deterministic_candidates` is not network-free: on an OCR cache miss it calls
    Gemini. If this filename drifts from the cache manager's, the check would report
    "offline-ready" for a pair that is not.
    """
    side = PairSide(
        drawing_id="D1",
        file_name="a.dxf",
        file_hash="H1",
        drawing_sha256="",
        entities_sha256="",
        entity_count=0,
    )
    expected = ComparisonCacheManager._get_ocr_cache_path("D1", "H1").name
    assert side.ocr_cache_filename() == expected


# ─── the committed manifest ───────────────────────────────────────────────────────────


def test_committed_manifest_is_readable_and_current():
    manifest = read_manifest(default_fixtures_dir())
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["guideline_version"] == GUIDELINE_VERSION, (
        "The manifest records which annotation guideline the corpus was built under. If "
        "the guideline moves, every pair needs re-labelling or discarding."
    )
    for entry in manifest.get("pairs") or []:
        assert entry["provenance"] in {"human", "mutation"}
        assert entry["label_state"] in {"unlabelled", "labelled", "burned"}


# ─── the eval seam itself ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deterministic_candidates_run_offline_over_a_real_pair():
    """Drive the real comparison engine from disk, with no Mongo and no network.

    This is the whole point of Stage 0b. It is skipped when the payloads are absent —
    they are gitignored by design, so this cannot run in CI until Stage 0c generates
    committable mutation pairs from a synthetic base drawing.
    """
    from services.backend.infrastructure.audit.comparison.orchestrator import (
        generate_deterministic_candidates,
    )

    corpus = load_corpus(fixtures_dir=default_fixtures_dir())
    if not corpus.pairs:
        pytest.skip("No pairs registered in the corpus manifest yet.")

    pair = corpus.pairs[0]
    try:
        ref_drawing, rev_drawing, ref_entities, rev_entities = pair.load()
    except CorpusPayloadMissingError:
        pytest.skip(f"Payloads for {pair.pair_id} are not on this machine (gitignored).")

    missing = pair.missing_ocr_cache()
    if missing:
        pytest.skip(f"{pair.pair_id} would make a live Gemini call: {missing}")

    candidates, rollups, warnings = await generate_deterministic_candidates(
        ref_drawing, rev_drawing, ref_entities, rev_entities
    )

    assert isinstance(candidates, list)
    # Every one of the six canonical categories must be present in the rollups, or the
    # Stage 0d scorer would silently score five.
    for category in TAXONOMY:
        assert category in rollups, f"rollups missing category {category!r}"
    assert isinstance(warnings, list)


# ─── guideline version: strict where it matters, tolerant where it must be ─────────────


def test_the_scorer_refuses_labels_from_an_older_guideline(tmp_path, monkeypatch):
    """`tools/eval.py` must keep the strict check. Mixing two definitions of "one finding"
    corrupts every metric derived from the corpus, and the corruption is invisible."""
    import services.backend.infrastructure.eval.corpus as corpus_mod

    raw = {
        "guideline_version": "1999-01-01",
        "findings": [],
    }
    with pytest.raises(corpus_mod.LabelSchemaError) as excinfo:
        corpus_mod.PairLabels.from_dict(raw, allow_stale_guideline=False)
    assert "1999-01-01" in str(excinfo.value)
    assert corpus_mod.GUIDELINE_VERSION in str(excinfo.value)


def test_management_commands_can_still_load_a_stale_corpus():
    """The guard must not block its own remedy.

    Bumping `GUIDELINE_VERSION` makes every existing label stale by definition. If the
    corpus-management commands enforced the same check as the scorer, `mutate` could not load
    the corpus whose labels it is about to regenerate, and `verify`/`status` could not report
    what needs regenerating — the version bump would be unrecoverable without hand-editing
    JSON. `tools/eval_corpus.py` therefore loads with `allow_stale_guideline=True` and prints
    which pairs are stale; only `tools/eval.py` is strict.
    """
    import services.backend.infrastructure.eval.corpus as corpus_mod

    stale = corpus_mod.PairLabels.from_dict(
        {"guideline_version": "1999-01-01", "findings": []},
        allow_stale_guideline=True,
    )
    assert stale.guideline_version == "1999-01-01", (
        "a tolerant load must preserve the stale version rather than silently restamping it "
        "— restamping would relabel by fiat, which is the corruption the guard exists to stop"
    )


# ── extraction provenance ─────────────────────────────────────────────────────────────
#
# A corpus payload freezes whatever the extractor produced on the day it was captured.
# Extraction-time fixes are baked in, so "which extractor made this?" is part of a pair's
# provenance — and until 2026-08-20 nothing recorded it, so the only way to ask was to read
# entity values and infer. These pin the field and, more importantly, the thing that reads it.


def test_a_payload_without_the_field_reads_as_unknown_not_as_version_zero():
    """Every pair committed before the field existed lacks it, and must still load.

    `0` is the unknown marker. The distinction matters at the point of use: an unknown
    capture and a capture from a genuinely ancient extractor need different messages, and
    presenting `0` as a real schema version would invent provenance that was never recorded.
    """
    from services.backend.infrastructure.eval.serialize import EvalDrawing

    legacy = EvalDrawing.from_dict(
        {"id": "x", "file_name": "f.dxf", "file_hash": "h", "entity_counts": {}}
    )
    assert legacy.extraction_schema_version == 0


def test_the_version_survives_the_payload_round_trip():
    from services.backend.infrastructure.eval.serialize import EvalDrawing

    drawing = EvalDrawing(
        id="x", file_name="f.dxf", file_hash="h", extraction_schema_version=5
    )
    assert EvalDrawing.from_dict(drawing.to_dict()).extraction_schema_version == 5


def test_the_manifest_side_carries_it_too():
    """So "was this pair captured from a stale drawing?" is answerable without a payload read."""
    from services.backend.infrastructure.eval.corpus import PairSide

    side = PairSide(
        drawing_id="d",
        file_name="f.dxf",
        file_hash="h",
        drawing_sha256="a",
        entities_sha256="b",
        entity_count=1,
        extraction_schema_version=6,
    )
    assert PairSide.from_dict(side.to_dict()).extraction_schema_version == 6
    assert PairSide.from_dict({"drawing_id": "d"}).extraction_schema_version == 0


def test_exporting_a_current_extraction_says_nothing():
    """The silence is the point: a warning that fires on every export is one nobody reads."""
    from services.backend.domain.models.extracted_entity import EXTRACTION_SCHEMA_VERSION
    from services.backend.infrastructure.eval.serialize import EvalDrawing
    from tools.eval_corpus import warn_if_stale_extraction

    current = EvalDrawing(
        id="x",
        file_name="f.dxf",
        file_hash="h",
        extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
    )
    assert warn_if_stale_extraction("ref", current) == []


def test_exporting_a_stale_extraction_names_both_versions():
    """A field nothing reads is the gap this repo just spent a session closing elsewhere.

    Export is the last cheap moment: afterwards the payload is sha256-frozen and its labels
    are authored against it, so a stale capture found later costs a re-export and a re-label.
    """
    from services.backend.infrastructure.eval.serialize import EvalDrawing
    from tools.eval_corpus import warn_if_stale_extraction

    lines = warn_if_stale_extraction(
        "rev",
        EvalDrawing(id="x", file_name="f.dxf", file_hash="h", extraction_schema_version=2),
    )
    assert len(lines) == 1
    assert "v2" in lines[0]
    assert "rev" in lines[0]


def test_an_unrecorded_extraction_gets_its_own_message():
    """Unknown is not the same claim as old, and the fix differs — say so."""
    from services.backend.infrastructure.eval.serialize import EvalDrawing
    from tools.eval_corpus import warn_if_stale_extraction

    lines = warn_if_stale_extraction(
        "ref",
        EvalDrawing(id="x", file_name="f.dxf", file_hash="h", extraction_schema_version=0),
    )
    assert len(lines) == 1
    assert "no extraction schema version" in lines[0]
    assert "v0" not in lines[0], "0 is the unknown marker, never a version to report back"
