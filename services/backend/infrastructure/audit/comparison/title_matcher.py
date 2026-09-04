"""Upper-left and bottom title-block key/value pairing.

Extracted from `orchestrator.generate_deterministic_candidates`, which was 1334 lines with
21 nested helpers -- a size at which none of this was reachable from a test except by
running the whole engine over a corpus pair.

Nothing here decides anything about the comparison. These functions read a sheet's
upper-left table and say which keys pair with which values; the orchestrator decides what
to do with the result. `extract_title_ul_kv` returns the entity ids it claimed rather than
subtracting them from the shared pool itself, which is what makes "only take content out of
the shared pool if you will compare it" checkable -- see CLAUDE.md's SRP section.

Depends only on `bom.zone_geometry` (a leaf). The orchestrator imports this module and
re-exports its public names, so the dependency runs one way:

    bom.zone_geometry -> title_matcher -> orchestrator
"""

from __future__ import annotations

from ..bom.zone_geometry import is_in_bbox

__all__ = [
    "UL_BAND_GAP_OUTLIER_FACTOR",
    "UL_COLUMN_SPLIT_RATIO",
    "extract_title_ul_kv",
    "match_title_ul_pairs",
    "partition_ul_pairs",
    "ul_value_band_index",
]


# Bilingual header equivalences for the title-upper-left metadata table.
#
# `_title_ul_tokens`' shared-token rule assumes that when the header banding differs by scale,
# whichever labels survive on the two drawings still overlap. That holds when one side keeps
# BOTH stacked labels ('Unit No. / ユニットNo.') and the other keeps one of them. It fails when
# the two sides keep DIFFERENT halves — measured live: the reference emitted `コードNO.` and the
# revision `PART NO.` for the same column, sharing no token, so the field never paired and its
# identical value 230 was reported twice (230 → NONE and NONE → 230).
#
# These four pairs are the English/Japanese labels of one JIS-style table, the same eight
# strings `vault_sync.get_upper_left_anchors()` already lists — as a flat list, with no record
# of which pair with which. Kept in code rather than sourced from the vault because
# `08 - Client Domain & CAD Rules/` is gitignored: a fix verifiable on exactly one machine is
# the failure mode this vault keeps having to record. A client using different terms should
# extend this tuple.
_TITLE_UL_SYNONYMS: tuple[frozenset[str], ...] = (
    frozenset({"unitno", "ユニットno"}),
    frozenset({"partno", "コードno"}),
    frozenset({"tqty", "総製作個数"}),
    frozenset({"stockqty", "在庫棚入庫"}),
)


def _ul_canonical(token: str) -> str:
    """A header token reduced to its letters, digits and CJK.

    `Part No.`, `PART NO` and `part　no.` all collapse to `partno`, so the synonym table does
    not have to enumerate punctuation and spacing variants of eight strings.
    """
    import re as _r
    return _r.sub(r"[^0-9a-z぀-ヿ一-鿿]", "", token or "")


def _ul_synonym_groups(tokens: set) -> set:
    """Indices of the synonym groups a key's tokens belong to."""
    canonical = {_ul_canonical(t) for t in tokens}
    return {i for i, group in enumerate(_TITLE_UL_SYNONYMS) if canonical & group}


def _title_ul_tokens(key: str) -> set:
    """Normalized header tokens of a title-upper-left key. A field's key is one or more
    stacked header labels joined by ' / ' (e.g. 'Unit No. / ユニットNo.'). Which labels land in
    the key depends on coordinate scale -- the header banding uses a fixed y-threshold, so a
    large-coordinate drawing splits the English and Japanese header rows into separate bands
    (both in the key) while a small-coordinate one merges them (only the nearest single label
    in the key). The same field therefore emits DIFFERENT combined keys on the two drawings."""
    import unicodedata as _u
    import re as _r
    def _n(t: str) -> str:
        return _r.sub(r"\s+", " ", _u.normalize("NFKC", t or "").strip().lower())
    return {_n(part) for part in str(key).split(" / ") if _n(part)}


#: A gap between column centres smaller than this fraction of the widest gap is within a
#: column, not between two. The upper-left table stacks a Japanese and an English label a
#: unit apart inside one cell, so a fixed tolerance cannot separate "same column" from
#: "next column" across the ~3x coordinate-scale difference between the two exporters.
UL_COLUMN_SPLIT_RATIO = 0.25

#: How much bigger than the table's own largest row gap a gap has to be before the band under
#: it is treated as content that drifted into the zone box rather than another table row.
#:
#: The usable window is narrow and was measured, not chosen: on M745227N01's reference the
#: stray note is 54.5 below a table whose largest row gap is 19.9 (ratio 2.74), while the
#: gap from the stacked bilingual header to the values row is 19.9 against the 9.9 between the
#: two header labels (ratio 2.01). Anything in (2.01, 2.74) separates them; 2.5 sits there
#: with +9.5% / -19.6% of margin. The 9.9 is what makes it tight -- it is two labels inside one
#: cell rather than two rows, so it understates the real row pitch.
UL_BAND_GAP_OUTLIER_FACTOR = 2.5


def _ul_columns(xs: list[float]) -> list[float]:
    """Column centres implied by one header row's text inserts.

    Splits on the *shape* of the gaps rather than an absolute distance: sorted x positions,
    cut wherever the step exceeds `UL_COLUMN_SPLIT_RATIO` of the largest step. On the
    reference sheet of M745227N01 the four header inserts are ~60 apart and there is nothing
    to merge; on the revision the same four columns are ~20 apart with the two stacked labels
    of each cell ~1 apart, and both resolve to 4 columns.
    """
    pts = sorted(x for x in xs if x is not None)
    if not pts:
        return []
    steps = [b - a for a, b in zip(pts, pts[1:], strict=False)]
    if not steps:
        return [pts[0]]
    split_at = max(steps) * UL_COLUMN_SPLIT_RATIO
    columns, current = [], [pts[0]]
    for step, x in zip(steps, pts[1:], strict=False):
        if step > split_at:
            columns.append(sum(current) / len(current))
            current = [x]
        else:
            current.append(x)
    columns.append(sum(current) / len(current))
    return columns


def ul_value_band_index(bands: list[list[tuple[float, float]]]) -> int:
    """Which band holds the table's VALUES — the row the checklist compares.

    This used to be `bands[-1]`, the lowest row, which is a positional assumption: it holds
    only while the zone box stops at the bottom of the table. It is the assumption that produced
    `[CHANGED] Title Block (Upper-Left) T. Q'ty / 総製作個数: 4 ロール：12 (2x6台) vs 16組`.

    What happened on `M745227N01`, measured: the only stored zone template is `aspect-1.374`
    flagged `is_default`, and this sheet is 1.414, so the fallback template's fractions scale
    onto a differently-shaped sheet -- the caveat [[Gotcha - Global Default Zone Template & the
    Aspect Caveat]] records. The reference's `title_upper_left` box came out with its bottom
    edge at y=762.99 while the table's value row sits at y=822, so a NOTE line at
    y=767.5 became the lowest band. It was read as the values row; the real values
    (`45 / 227 / 16組 / 0`) were demoted to a header band; and the note inherited the key
    `T. Q'ty / 総製作個数` because its x lands 2.4 units nearer that column than the next
    one along. Nothing in the path ever asked whether what it found looked like a value.

    Two independent structural signals say a band is not the values row, and a band has to fail
    both before it is dropped:

    1. Column coverage. A values row fills the table's columns. The real one covers 4 of 4;
       the stray note covers 1 of 4.
    2. Row pitch. Rows of one table sit a consistent distance apart -- 9.9 and 19.9 here --
       and content that drifted in does not: the note is 54.5 below the row above it.

    Requiring both is what keeps a legitimately sparse values row (one cell filled, three empty)
    from being discarded: it fails coverage but sits at the table's own pitch, so it survives.
    And at least two bands always remain, because a table with no header row above its values
    is not a table this extractor can read.

    The walk runs TOP-DOWN, cutting at the first band that fails both, rather than popping from
    the bottom. Popping was written first and had the yardstick eat itself: judging the last
    band against "the largest gap above it" includes the strays already under suspicion, so a
    second stray note 24.2 below the first was measured against the first's own 54.5 and kept.
    Walking down compares each gap only against gaps already accepted as table rows.

    `bands` are (x, y) inserts, ordered top to bottom. Returns an index into `bands`.
    """
    if len(bands) < 3:
        return len(bands) - 1

    def band_y(band: list[tuple[float, float]]) -> float:
        return max(y for _, y in band) if band else 0.0

    columns = _ul_columns([x for x, _ in bands[0]])
    if not columns:
        return len(bands) - 1

    pitches = sorted(b - a for a, b in zip(columns, columns[1:], strict=False))
    # Half the typical column pitch: a value is inset from its header (measured at 27-35% of
    # the pitch on both exporters) but never reaches the next column. One column means no
    # pitch, so nothing is excluded on that basis.
    tolerance = (pitches[len(pitches) // 2] / 2.0) if pitches else float("inf")

    def fills_columns(band: list[tuple[float, float]]) -> bool:
        covered = {
            min(range(len(columns)), key=lambda i: abs(columns[i] - x))
            for x, _ in band
            if min(abs(c - x) for c in columns) <= tolerance
        }
        return len(covered) >= max(1, len(columns) // 2)

    ys = [band_y(b) for b in bands]
    gaps = [a - b for a, b in zip(ys, ys[1:], strict=False)]

    accepted: list[float] = []
    for i in range(1, len(bands)):
        gap = gaps[i - 1]
        # `i >= 2` keeps at least a header row and a values row: band 1 is never cut, and it
        # also guarantees `accepted` is non-empty by the time it is used as the yardstick.
        outlying = gap > max(accepted) * UL_BAND_GAP_OUTLIER_FACTOR if accepted else False
        if i >= 2 and outlying and not fills_columns(bands[i]):
            return i - 1
        accepted.append(gap)

    return len(bands) - 1


def partition_ul_pairs(
    matched: list,
    *,
    corroborates,
    covered_by_another_zone,
) -> tuple[list, list]:
    """Split matched upper-left pairs into (comparable, released).

    Claim only what can be compared. A value pulled out of the upper-left box with nothing
    on the other side to compare it against is not a comparison result — it is a value this
    extractor should not have taken. Reporting it as REMOVED/ADDED asserts a change nobody
    measured, and `_collect_structured_text_values` then suppresses that text sheet-wide, so the
    zone it really belongs to cannot report it either. One over-reaching zone box on
    `M745227N01` turned `4 ロール：12 (2x6台)` into a false CHANGED against `16組` *and* a false
    ADDED against a line the reference plainly has.

    Three outcomes, in order:

    1. Both sides have a value → comparable, always.
    2. One side only, but the other side's UL box contains that text → comparable. The field
       was mis-extracted, not changed; the emit loop's bilateral corroboration guard turns it
       into MATCHED. That is still a comparison.
    3. One side only, nothing anywhere → released *if* another zone's shape covers the
       value's own coordinates, so that zone's pass will compare it. Otherwise it stays
       comparable and the one-sided report stands.

    Rung 3's condition is the whole safety of this. `title_upper_left` is in
    `VIEWS_EXCLUDED_ZONES`, so content inside that box is subtracted from the `views` pool and
    no other pass is scoped to it. Releasing with no catcher would be a silent false
    negative — the one failure mode this system cannot detect. Zones overlap, which is what
    makes release possible at all: on M745227N01 the roll-count line released here lands inside
    `notes` on the reference, and comes back as a real CHANGED against its revision counterpart.
    With no catcher, reporting a value nobody could pair beats deleting it — a wrong finding is
    visible, a missing one is not.

    `corroborates(value, missing_side)` searches the side that lacks the value; `missing_side`
    is `"ref"` or `"rev"`. `covered_by_another_zone(coords, side)` asks whether any zone other
    than `title_upper_left` covers that point on the side the value came from.
    """
    comparable: list = []
    released: list = []
    for ref_p, rev_p in matched:
        ref_val = (ref_p or {}).get("value")
        rev_val = (rev_p or {}).get("value")
        if ref_val and rev_val:
            comparable.append((ref_p, rev_p))
            continue

        lone = ref_p if ref_val else rev_p
        value = ref_val or rev_val
        side = "ref" if ref_val else "rev"
        missing_side = "rev" if ref_val else "ref"
        if not value:
            comparable.append((ref_p, rev_p))
        elif corroborates(value, missing_side):
            comparable.append((ref_p, rev_p))
        elif covered_by_another_zone((lone or {}).get("coords"), side):
            released.append(lone)
        else:
            comparable.append((ref_p, rev_p))
    return comparable, released


def match_title_ul_pairs(ref_pairs: list, rev_pairs: list) -> list:
    """Greedy-match reference↔revision title-upper-left pairs by shared header token, so the
    same field pairs up even when the two drawings emitted different combined keys (see
    _title_ul_tokens). Returns [(ref_pair | None, rev_pair | None), ...]; a one-sided tuple is
    a genuinely added/removed field. Replaces an exact-combined-key lookup that double-reported
    every identical value as REMOVED + ADDED whenever the header banding differed by scale."""
    rev_unmatched = list(rev_pairs)
    matched: list = []
    for ref_p in ref_pairs:
        rt = _title_ul_tokens(ref_p.get("key", ""))
        rg = _ul_synonym_groups(rt)
        # Shared token first — the common case, and exact. Only when that finds nothing do we
        # fall back to the synonym table, so an English/Japanese equivalence can never override
        # a literal match that was already available.
        hit = next((rp for rp in rev_unmatched if rt & _title_ul_tokens(rp.get("key", ""))), None)
        if hit is None and rg:
            hit = next(
                (rp for rp in rev_unmatched if rg & _ul_synonym_groups(_title_ul_tokens(rp.get("key", "")))),
                None,
            )
        if hit is not None:
            rev_unmatched.remove(hit)
            matched.append((ref_p, hit))
        else:
            matched.append((ref_p, None))
    for rev_p in rev_unmatched:
        matched.append((None, rev_p))
    return matched


def extract_title_ul_kv(entities: list, bbox) -> list:
    """Spatially pair header/label texts with their value texts inside bbox.
    DXF uses Y-up coordinates — larger Y is physically higher on the sheet.
    Headers sit ABOVE values, so headers have larger Y values.
    Returns list of {key, value, coords} dicts sorted left-to-right.

    Do not re-add a "subtract the sibling zones' shapes before banding" filter here
    without measuring the DETECTION path. One was written and reverted on 2026-08-12. It
    was aimed at a real defect — with no template the UL box swallows the notes block, whose
    lines sit at the table's own pitch and align to a column, so
    `[CHANGED] Part No. / コードNo.: 227 vs 完成時、バリ、キリ粉はなきこと` compared a
    deburring sentence against a part number — and on the three unlabelled sheets it was
    eyeballed on it did exactly what it promised.

    On the scored corpus it was a regression: detection-only F1 0.7736 → 0.7339,
    fp 10 → 14, tp 41 → 40, and 3 new `title_block` false positives including the very
    `在庫棚入庫: 0 vs Ｃ１` it was supposed to remove. The mechanism is an interaction: the
    subtraction changes which entities remain, which changes the band structure, and
    `ul_value_band_index` then cuts in the wrong place. Alone, the band chooser costs
    nothing; alone, the subtraction costs 0.7736 → 0.7547; together, 0.7339.

    Two lessons worth more than the code was:
    1. The templated baseline cannot see any of this. All three v46 mechanisms measure
       byte-identical at F1 0.9231 with templates pinned, because pinned boxes do not
       over-reach so none of them ever fires. The only baseline being run was blind to the
       entire change.
    2. Eyeballing unlabelled sheets is not measurement. The improvement was real on the
       sheets it was checked on and negative on the corpus that scores.

    Zone ownership is the right idea and it is being rebuilt as one explicit, tested
    arbitration rather than a per-call-site exclusion list — see `zone_ownership.py`.
    """
    import unicodedata as _ud
    def _ul_norm(t: str) -> str:
        t = _ud.normalize("NFKC", t or "").strip().lower()
        import re as _re
        return _re.sub(r"\s+", " ", t)

    if not bbox:
        return [], set()
    inside = [
        e for e in entities
        if getattr(e, 'entity_type', '') in ('text', 'mtext', 'attrib')
        and is_in_bbox(e, bbox)
    ]
    if not inside:
        return [], set()

    # Frame grid references (single chars at the sheet edge) can leak into the UL zone;
    # exclude them. The edge is measured RELATIVE to the zone bbox, not with absolute
    # vx<25/vy>285: those constants only hold in the small coordinate space, and on a
    # large-coordinate drawing they dropped a legitimate single-digit UL VALUE (a '0'
    # Stock Q'ty at y~822) as if it were a top-margin grid label.
    _bw = (bbox[2] - bbox[0]) or 1.0
    _bh = (bbox[3] - bbox[1]) or 1.0

    def is_grid_label(e):
        t = (getattr(e, 'properties', {}) or {}).get('text', '').strip()
        if len(t) <= 1 or any(c in t for c in "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"):
            vx = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0]
            vy = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1]
            if vx < bbox[0] + 0.08 * _bw or vy > bbox[3] - 0.08 * _bh:
                return True
        return False

    inside = [e for e in inside if not is_grid_label(e)]
    if not inside:
        return [], set()

    inside.sort(key=lambda x: getattr(x, 'geometry', {}).get('insert', [0, 0, 0])[1], reverse=True)
    bands: list[list] = []
    current_band = []
    for e in inside:
        if not current_band:
            current_band.append(e)
        else:
            prev_y = getattr(current_band[-1], 'geometry', {}).get('insert', [0, 0, 0])[1]
            ey = getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1]
            if abs(prev_y - ey) <= 4.0:
                current_band.append(e)
            else:
                bands.append(current_band)
                current_band = [e]
    if current_band:
        bands.append(current_band)

    if len(bands) < 2:
        return [], set()

    # NOT `bands[-1]`. The lowest band is the values row only while the zone box stops at
    # the bottom of the table; when it over-reaches, a note becomes the "values" and the
    # real values become headers. See ul_value_band_index.
    _value_idx = ul_value_band_index([
        [(
            getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0],
            getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[1],
        ) for e in band]
        for band in bands
    ])
    if _value_idx < 1:
        return [], set()

    value_band = sorted(bands[_value_idx], key=lambda e: getattr(e, 'geometry', {}).get('insert', [0, 0, 0])[0])
    header_bands = bands[:_value_idx]

    # What this table actually CLAIMS: the header bands and the value band. The bands below
    # the value row are the ones `ul_value_band_index` cut as content that drifted into the
    # box, and they are claimed by nothing here.
    #
    # This set is what the `views` pool subtracts, instead of the whole UL bounding box —
    # and the difference is a silent false negative. Reported by the owner on M745227N01:
    # `４ロール：１２（２×６台）` came out ADDED with no REMOVED counterpart on a sheet that
    # plainly carries it on both sides. The reference's copy sits at y=767.5 and the UL box
    # bottom edge is at y=763.0, so it is 4.5 units inside — while its sibling 24 units
    # lower falls outside and pairs correctly, which is why one of the two lines was right.
    # `title_upper_left` is in VIEWS_EXCLUDED_ZONES, so the box removed the reference's copy
    # from the only pool that could have matched it, and the extractor had already rejected
    # it as not-a-values-row. Claimed by the zone for exclusion, unclaimed by it for
    # comparison, compared by nobody.
    claimed = {id(e) for band in bands[:_value_idx + 1] for e in band}

    all_xs = [getattr(e, 'geometry', {}).get('insert', [0])[0] for e in inside]
    band_width = (max(all_xs) - min(all_xs)) if len(all_xs) > 1 else 9999.0
    max_pair_dist = max(band_width / max(len(value_band), 1) * 1.5, 30.0)

    pairs = []
    for val_e in value_band:
        vx = getattr(val_e, 'geometry', {}).get('insert', [0, 0, 0])[0]
        vy = getattr(val_e, 'geometry', {}).get('insert', [0, 0, 0])[1]
        val_text = (getattr(val_e, 'properties', {}) or {}).get('text', '').strip()
        if not val_text or len(val_text) <= 0:
            continue

        header_parts = []
        for hband in header_bands:
            closest_hdr = min(
                hband,
                key=lambda h: abs(getattr(h, 'geometry', {}).get('insert', [0, 0, 0])[0] - vx),
                default=None
            )
            if closest_hdr:
                dist = abs(getattr(closest_hdr, 'geometry', {}).get('insert', [0, 0, 0])[0] - vx)
                if dist <= max_pair_dist:
                    hdr_text = (getattr(closest_hdr, 'properties', {}) or {}).get('text', '').strip()
                    if hdr_text and hdr_text not in header_parts and not hdr_text.isdigit():
                        header_parts.append(hdr_text)

        header_parts.reverse()
        header_parts = [
            p for p in header_parts 
            if not (p.startswith('①') or p.startswith('②') or p.startswith('③') or p.startswith('④') or p.strip().isdigit())
        ]

        combined_key = " / ".join(header_parts) if header_parts else "Value"
        pairs.append({'key': combined_key, 'value': val_text, 'coords': [vx, vy]})
    return pairs, claimed
