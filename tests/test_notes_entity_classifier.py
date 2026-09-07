"""Per-entity notes classification — is this text a note, regardless of which box it fell in.

The defect this replaces, measured on `M7452A0N01-rev-mut005`: both sides carry the same four
notes rows at IDENTICAL coordinates, the reference's detected notes box is (38.0, 202.6, 60.0,
251.0) and the revision's is (65.0, 202.6, 254.0, 231.8), so every row is inside one and outside
the other and reports `REMOVED` on a sheet that plainly has it. The cause is the mutation itself
— it adds `追加注記` at x=264, a legitimate `注記` anchor 209 units from the block, and the
anchor-cluster detector cannot represent two clusters so it grows a box covering neither.
"""

from services.backend.infrastructure.audit.comparison.notes_classifier import (
    COHESION_MAX_LEN,
    NOTE_SEED_MIN_LEN,
    classify_notes,
    is_note_sentence,
)

# The real notes block from M745203N01/rev, coordinates as measured.
BLOCK = [
    ("タップ、キリ穴は面取り仕上げのこと", 55.0, 248.5),
    ("１", 43.0, 248.5),
    ("指示なき角部は糸面取りのこと", 55.0, 238.9),
    ("完成時、バリ、キリ粉はなきこと", 55.0, 229.3),
]


# --- content predicate ------------------------------------------------------


def test_instruction_sentences_are_notes():
    for text in (
        "指示なき角部は糸面取りのこと",
        "タップ、キリ穴は面取り仕上げのこと",
        "完成時、バリ、キリ粉はなきこと",
        "注１．グラインダ－ニテ滑ラカニ仕上ゲノコト。",
    ):
        assert is_note_sentence(text), text


def test_specification_lines_are_notes():
    assert is_note_sentence("素材調質施工　硬度HS35～38度")
    assert is_note_sentence("イソナイト施工　硬度ＨＶ５００　ＵＰ")


def test_an_instruction_survives_a_trailing_edit():
    """A note does not stop being one because a revision appended to it. An exact `endswith`
    scored `指示なき角部は糸面取りのこと2` as not-a-note on the revision side ONLY — an asymmetry,
    which is the exact failure this module exists to remove."""
    assert is_note_sentence("指示なき角部は糸面取りのこと2")
    assert is_note_sentence("完成時、バリ、キリ粉はなきことB")


def test_a_strong_marker_seeds_below_the_length_floor():
    """`追加注記` is 4 characters and is the corpus's one ADDED-note label. Applying the length
    gate first made the classifier miss the single finding it exists to catch."""
    assert len("追加注記") < NOTE_SEED_MIN_LEN
    assert is_note_sentence("追加注記")


def test_the_english_word_note_seeds_but_the_abbreviation_no_does_not():
    """`ZONE_ANCHORS` carries `note:`/`notes:` WITH the colon, which misses a bare `NEW NOTE`.
    Word-bounded so it cannot fire on `No.`, which is on every sheet twice."""
    assert is_note_sentence("NEW NOTE")
    assert is_note_sentence("GENERAL NOTES")
    assert is_note_sentence("ＮＯＴＥ")
    assert not is_note_sentence("コードNo.")
    assert not is_note_sentence("設計訂正書No.")
    assert not is_note_sentence("ユニットNo.")


def test_table_furniture_and_short_markers_are_not_notes_on_content_alone():
    for text in (
        "備     考", "寸 法 区 分", "6.3S ～ 1.6S", "素材重量 Kg",
        "コードNo.", "Kusakabe Electric ＆ Machinery Co.,Ltd.",
        "１", "C1", "45", "227", "発注",
    ):
        assert not is_note_sentence(text), text


def test_the_drawing_title_is_not_a_note():
    """`ロールカセット 12\"ミル` is why `ロール` was measured and rejected as a zone anchor."""
    assert not is_note_sentence('ロールカセット 12"ミル')


def test_roll_counts_are_deliberately_not_seeds():
    """They sit inside the pinned notes box on some sides and in `views` on others. Claiming
    them moves content between categories, so it is a separate measured change, not a freebie."""
    assert not is_note_sentence("4 ロール：12 (2x6台)")
    assert not is_note_sentence("２ロール：　４（２×２台）")


# --- the ownership veto -----------------------------------------------------


def test_the_tolerance_block_instruction_is_vetoed_not_argued_with():
    """`必要な場合は、粗さ区分を記入のこと` reads as a note by every content rule there is. It is
    excluded because `tolerance` outranks `notes` — a real ruled box against no box at all."""
    text = "必要な場合は、粗さ区分を記入のこと"
    assert is_note_sentence(text)
    assert classify_notes([(text, 5.0, 5.0)], {"tolerance": (0, 0, 10, 10)}) == []
    assert classify_notes([(text, 5.0, 5.0)], {}) == [0]


def test_an_over_reaching_title_upper_left_box_cannot_veto_a_note():
    """Regression on a measured mistake: ranking `title_upper_left` above `notes` dropped
    notes_section recall to 0.54, because its DETECTED box swallows the whole notes block."""
    regions = {"title_upper_left": (0.0, 0.0, 500.0, 500.0)}
    got = classify_notes(BLOCK, regions, sheet_span=500.0)
    assert [BLOCK[i][0] for i in got] == [t for t, _x, _y in BLOCK]


# --- cohesion ---------------------------------------------------------------


def test_the_item_number_joins_its_own_sentence():
    got = classify_notes(BLOCK, {}, sheet_span=500.0)
    assert "１" in [BLOCK[i][0] for i in got]


def test_a_distant_seed_does_not_widen_the_block_it_is_not_part_of():
    """`追加注記` sits at x=264 while the block is at x=55. A cohesion window spanning both
    admitted anything sharing a row anywhere across the sheet — the view label `Ａ` and the
    chamfer callout `Ｃ１`. Cohesion is measured against ONE seed, in both axes."""
    items = BLOCK + [
        ("追加注記", 264.0, 213.0),
        ("Ａ", 262.0, 219.0),      # shares a row with a block sentence, 200+ units away
        ("Ｃ１", 250.0, 248.5),     # shares a row with the first sentence
    ]
    got = {items[i][0] for i in classify_notes(items, {}, sheet_span=500.0)}
    assert "追加注記" in got
    assert "Ａ" not in got
    assert "Ｃ１" not in got


def test_cohesion_only_admits_item_markers_not_callouts():
    """`追加 3-M8` is a drawing callout that happened to share a row with a note."""
    items = BLOCK + [("追加 3-M8", 60.0, 238.9)]
    got = {items[i][0] for i in classify_notes(items, {}, sheet_span=500.0)}
    assert "追加 3-M8" not in got
    assert len("追加 3-M8") > COHESION_MAX_LEN


def test_a_cohered_marker_is_still_subject_to_the_veto():
    """A `1` inside the BOM stays the BOM's, however close a note happens to be."""
    items = BLOCK + [("9", 44.0, 229.3)]
    regions = {"bom": (40.0, 225.0, 50.0, 235.0)}
    got = {items[i][0] for i in classify_notes(items, regions, sheet_span=500.0)}
    assert "9" not in got


def test_nothing_is_claimed_without_a_seed():
    """Cohesion never bootstraps itself — item markers alone are not a notes block."""
    assert classify_notes([("１", 43.0, 248.5), ("2", 43.0, 238.9)], {}) == []


# --- the property that matters ----------------------------------------------


def test_the_same_text_classifies_the_same_on_both_sides():
    """The whole point. The two sides of a comparison detect their zones independently; a
    content predicate cannot disagree with itself."""
    ref = classify_notes(BLOCK, {"notes": (38.0, 202.6, 60.0, 251.0)}, sheet_span=500.0)
    rev = classify_notes(BLOCK, {"notes": (65.0, 202.6, 254.0, 231.8)}, sheet_span=500.0)
    assert ref == rev == [0, 1, 2, 3]


def test_empty_and_degenerate_inputs():
    assert classify_notes([], {}) == []
    assert classify_notes([("", 0.0, 0.0)], {}) == []
    assert classify_notes([("完成時、バリ、キリ粉はなきこと", 1.0, 1.0)], None) == [0]
