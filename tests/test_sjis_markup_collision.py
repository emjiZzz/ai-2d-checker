"""Tests that Shift-JIS characters survive MTEXT cleaning.

A DXF is read byte-preserving (`encoding="latin-1"`) so `dxf_parser.transcode_value` can
recover real Shift-JIS text afterwards. Everything before that pass — including
`EntityMapper._clean_mtext_content` → `strip_mtext` — therefore operates on raw CP932 bytes.

CP932 trail bytes may be 0x5C, 0x7B, 0x7D or 0x7E: backslash and braces, exactly the MTEXT
markup characters. Stripping markup on the byte string mutilated any character whose second
byte was one of them. Observed in the entities as *stored* on real customer drawings:

    素材調質施工    ->  素材調質詩H      (施 = 0x8E 0x7B, trail eaten as `{`)
    イソナイト施工  ->  イャiイト詩H     (ソ = 0x83 0x5C, the escape rule ate the next byte too)

Not cosmetic: `ZONE_ANCHORS["tolerance"]` contains 表示外公差 and 表 is 0x95 0x5C, so that
anchor could never match stored text.
"""
import pytest

from services.backend.infrastructure.utils.text import strip_mtext

# Characters whose CP932 trail byte collides with MTEXT markup.
DANGEROUS = {
    "施": 0x7B,   # {
    "ソ": 0x5C,   # backslash
    "表": 0x5C,
    "十": 0x5C,
    "能": 0x5C,
    "予": 0x5C,
}


def _as_raw_bytes(text: str) -> str:
    """What the parser hands to strip_mtext: CP932 bytes held one-per-char in a str."""
    return text.encode("cp932").decode("latin-1")


def _transcode(text: str) -> str:
    """What dxf_parser.transcode_value does afterwards."""
    return text.encode("latin-1").decode("cp932")


def _round_trip(text: str) -> str:
    """Full pipeline: byte-preserving read -> strip_mtext -> transcode."""
    return _transcode(strip_mtext(_as_raw_bytes(text), convert_symbols=False))


@pytest.mark.parametrize("char,trail", sorted(DANGEROUS.items()))
def test_dangerous_trail_byte_is_documented_correctly(char, trail):
    """Guards the premise: these really do have a markup byte as their second byte."""
    assert char.encode("cp932")[1] == trail


@pytest.mark.parametrize("text", [
    "素材調質施工　硬度HS35～38度",
    "イソナイト施工　硬度HV500up",
    "表示外公差",
    "指示外公差",
    "施工",
    "ソ",
    "十能予表",
])
def test_japanese_text_survives_the_pipeline(text):
    assert _round_trip(text) == text


def test_the_exact_reported_corruptions():
    """The two strings observed corrupted in the database."""
    assert _round_trip("素材調質施工") == "素材調質施工"
    assert "詩H" not in _round_trip("素材調質施工")

    assert _round_trip("イソナイト施工") == "イソナイト施工"
    assert "ャi" not in _round_trip("イソナイト施工")


def test_tolerance_anchor_survives():
    """The functional consequence: this anchor must be matchable in stored text."""
    assert _round_trip("表示外公差") == "表示外公差"


# ---------------------------------------------------------------------------
# Markup must still be stripped
# ---------------------------------------------------------------------------

def test_real_mtext_markup_is_still_removed():
    raw = _as_raw_bytes("表示外公差")
    # A genuine MTEXT width code and font group wrapped around protected characters.
    decorated = "{\\W0.8;" + raw + "}"

    assert _transcode(strip_mtext(decorated, convert_symbols=False)) == "表示外公差"


def test_paragraph_break_is_still_converted():
    raw = _as_raw_bytes("施工")
    assert _transcode(strip_mtext(raw + "\\P" + raw, convert_symbols=False)) == "施工 施工"


def test_markup_between_protected_characters_is_removed():
    a, b = _as_raw_bytes("施"), _as_raw_bytes("表")
    assert _transcode(strip_mtext(a + "\\H2.5;" + b, convert_symbols=False)) == "施表"


def test_ascii_only_behaviour_is_unchanged():
    assert strip_mtext("{\\W0.8;PLAIN}", convert_symbols=False) == "PLAIN"
    assert strip_mtext("A\\PB", convert_symbols=False) == "A B"


def test_symbol_conversion_still_works_on_decoded_text():
    assert strip_mtext("%%c25", convert_symbols=True) == "Ø25"


def test_already_decoded_unicode_is_left_to_the_original_path():
    """Post-transcode callers (zone_detector, table_extractor) pass real Unicode. It is not
    latin-1 encodable, so masking is skipped — there are no raw trail bytes to protect."""
    assert strip_mtext("素材調質施工", convert_symbols=True) == "素材調質施工"
    assert strip_mtext("{\\W0.8;素材調質施工}", convert_symbols=True) == "素材調質施工"


def test_masking_survives_a_stripped_group_without_misaligning():
    """A placeholder deleted along with its enclosing markup must not shift the others.

    This is why each masked character gets its own placeholder rather than a shared one.
    """
    keep = _as_raw_bytes("施表十")
    assert _transcode(strip_mtext(keep, convert_symbols=False)) == "施表十"


def test_empty_and_none_inputs():
    assert strip_mtext("") == ""
    assert strip_mtext(None) == ""
