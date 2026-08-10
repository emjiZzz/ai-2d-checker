"""A short structured value must not suppress its own twin elsewhere on the sheet.

Values captured by structured title-block/BOM extraction are excluded from the generic
zone passes so they are not reported twice (`_collect_structured_text_values` in
`orchestrator.generate_deterministic_candidates`). That net is keyed on TEXT ALONE and applied
sheet-wide, so before `min_structured_value_length` a value short enough to recur innocently
suppressed every occurrence of that string in every zone, on **both** sides -- which makes the
suppressed content's deletion unreportable rather than merely unreported.

Measured on `M7452A0N01-rev-mut012`: the BOM row is numbered `1`, the notes zone contains a
standalone full-width `１` (NFKC-folds to `1`), and deleting it produced no finding at all.
Renumbering the BOM row to `999` made the missing REMOVED finding appear -- the engine's only
reason for silence was the string collision.

This is the false-negative class the project's gap analysis says has never been measured, and it
is invisible to the duplicate counter for the same reason recorded in
[[Gotcha - Title Block QTY Reads the Upper-Left Table]]: nothing was reported, so nothing could
be counted as a duplicate.

See docs/vault/06 - .../Gotcha - A Short Structured Value Suppresses Its Own Zone.
"""

import pytest

from services.backend.infrastructure.audit.comparison.params import (
    DEFAULT_PARAMS,
    current_params,
    sweep_override,
)

_PAIR_ID = "M7452A0N01-rev-mut012"


def _normalized(text) -> str:
    import unicodedata

    return unicodedata.normalize("NFKC", str(text or "")).strip()


def _load_pair():
    from services.backend.infrastructure.eval.corpus import (
        CorpusPayloadMissingError,
        default_fixtures_dir,
        load_corpus,
    )

    corpus = load_corpus(fixtures_dir=default_fixtures_dir())
    match = [p for p in corpus.pairs if p.pair_id == _PAIR_ID]
    if not match:
        pytest.skip(f"{_PAIR_ID} is not registered in this corpus.")
    try:
        match[0].load()
    except CorpusPayloadMissingError:
        pytest.skip("Corpus payloads are gitignored and not on this machine.")
    return match[0]


def test_the_default_floor_is_three():
    """3 is a convention, not a measured optimum -- it is the shortest length at which the
    corpus's real structured values (`8.65`, `5.31`, `M745203N01`) are all still caught.
    Pinned so a future change is a decision rather than a drift."""
    assert DEFAULT_PARAMS.min_structured_value_length == 3
    assert current_params().min_structured_value_length == 3


@pytest.mark.asyncio
async def test_a_bom_row_number_does_not_silence_a_notes_glyph():
    """The regression. Verified to fail at a floor of 1, which is the pre-fix behaviour."""
    from services.backend.infrastructure.eval.runner import run_pair

    pair = _load_pair()
    predictions, _ = await run_pair(pair)

    notes_ones = [
        p for p in predictions
        if _normalized(getattr(p, "new_text", None) or getattr(p, "ref_text", None)) == "1"
        and p.category == "notes_section"
    ]
    assert len(notes_ones) == 1, (
        "the deleted notes '1' was not reported; a BOM row numbered '1' is suppressing it "
        f"sheet-wide. Got: {[(p.status, p.new_text, p.ref_text) for p in predictions]}"
    )
    assert notes_ones[0].status == "REMOVED"


@pytest.mark.asyncio
async def test_a_floor_of_one_reproduces_the_defect():
    """The other direction, so the test cannot pass for an unrelated reason. At a floor of 1
    every structured value re-enters the net and the finding disappears again -- which is what
    makes this a test of the mechanism rather than of the corpus."""
    from services.backend.infrastructure.eval.runner import run_pair

    pair = _load_pair()
    with sweep_override(DEFAULT_PARAMS.with_value("min_structured_value_length", 1)):
        predictions, _ = await run_pair(pair)

    notes_ones = [
        p for p in predictions
        if _normalized(getattr(p, "new_text", None) or getattr(p, "ref_text", None)) == "1"
        and p.category == "notes_section"
    ]
    assert notes_ones == [], (
        "expected the pre-fix defect to reproduce at a floor of 1. If this fails, the "
        "suppression no longer runs through _collect_structured_text_values and the guard "
        "above is passing for a different reason than it claims."
    )
