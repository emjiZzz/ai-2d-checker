"""
notes_classifier.py
===================
Is this text a note? Answered from the text itself and its neighbours, not from a box.

## Why the box cannot answer it

`notes` is the one zone with no drawn boundary on these sheets. The ruled-border spike
measured a best-IoU ceiling of 0.08 for it — chosen knowing the answer, so that bounds any
rule rather than describing one — because its best candidate is the whole sheet frame. The
"notes zone" is a rectangle *we* impose on text that floats inside the frame, which is why every
approach so far produced a different arbitrary box.

The cost is measured. Detection-only, `notes_section` scores P 0.59 / R 1.00: recall is
perfect, so the box already catches every real change and only *adds*. That signature has one
cause, and it is not tuning.

On `M7452A0N01-rev-mut005` both sides carry the same four notes rows at identical
coordinates, and:

    REF  notes box = (38.0, 202.6,  60.0, 251.0)   -> all four rows INSIDE
    REV  notes box = (65.0, 202.6, 254.0, 231.8)   -> all four rows OUTSIDE

The mutation adds the text `追加注記` at x=264 — a legitimate `注記` anchor, 209 units from
the real notes cluster at x=55. The anchor-cluster detector cannot represent two clusters, so it
grows a box spanning x 65-254 that covers neither, and every notes row reports `REMOVED` on
a sheet that plainly has them. Seven false positives from one added note.

Adding a note destroys the notes zone. This is the same failure mode as the `仕上げ` anchor
removed on 2026-08-12 for matching `仕上げ記号` in the tolerance block — except that anchor was
wrong and could be deleted, while `注記` is the canonical Japanese word for "notes" and cannot
be. The approach is structurally fragile, not mis-tuned. See
docs/vault/06 - .../Gotcha - Adding a Note Destroys the Notes Zone.

A content predicate is side-independent, so both sides classify identically no matter where the
box went. That is the whole mechanism.

## What a note looks like here, measured

Taken from the text inside the pinned notes box across the corpus — the configuration that
scores P 1.00 / R 1.00, so it is the closest thing to a label this corpus has:

| kind | examples | len |
| :--- | :--- | ---: |
| instruction | `指示なき角部は糸面取りのこと`, `タップ、キリ穴は面取り仕上げのこと` | 14-17 |
| instruction | `完成時、バリ、キリ粉はなきこと` | 15 |
| numbered | `注１．グラインダ－ニテ滑ラカニ仕上ゲノコト。` | 22 |
| spec | `素材調質施工　硬度HS35～38度`, `イソナイト施工　硬度HV500up` | 17-18 |
| item marker | `１`, `1`, `a`, `b`, `c`, `d`, `C1` | 1-2 |

The item markers are the reason content alone is not enough: nothing about `１` says "note". It
is a note because it sits on the same row as an instruction, 12 units to its left. So the
pass is two-stage — seed on content, then admit neighbours by cohesion.

The nearest negative is the one that decides the design. The tolerance block contains
`必要な場合は、粗さ区分を記入のこと` — an instruction ending in `のこと`, identical in form to a
real note. No content rule separates it. It is excluded because `tolerance` outranks `notes`
in `zone_ownership` (a real ruled box, IoU 0.85, against no box at all), which is why the veto
is not optional and why this module refuses to run without `regions`.

`ロール：` is deliberately not a seed token, though `4 ロール：12 (2x6台)` does sit inside
the pinned box on some sides. Those lines land in `views` on others, so claiming them moves
content between categories on a corpus whose labels come from the engine's own pool. Measure it
as a separate change if it is wanted. Note this is a different mechanism from the vault's on
adding `ロール` to `ZONE_ANCHORS` — that one *grew a box*; this one would only label an entity —
but the caution transfers.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Sequence

from ..bom.zone_detector import ZONE_ANCHORS
from ..bom.zone_ownership import is_owned_by_other

#: Shortest text that can SEED the notes block on content alone. Every instruction and spec line
#: measured on the corpus is 14-22 characters; the longest confusable non-note single tokens in
#: the sibling zones are 6-11 (`寸 法 区 分`, `6.3S ～ 1.6S`). 6 keeps the door shut on table
#: headers while leaving 8 characters of margin under the shortest real note.
NOTE_SEED_MIN_LEN = 6

#: Sentence-final forms of a Japanese work instruction. `こと` covers `のこと` and `なきこと`;
#: `ノコト` is the katakana spelling used on the older sheets (`仕上ゲノコト。`).
_INSTRUCTION_ENDINGS = ("こと", "ノコト", "事", "。")

#: Unambiguous note markers. These seed at any length, bypassing `NOTE_SEED_MIN_LEN`,
#: because they name the thing outright and nothing else on these sheets contains them.
#:
#: The length bypass is not a nicety. `追加注記` ("additional note") is 4 characters and is
#: the mutation under test on `M7452A0N01-rev-mut011` — the corpus's one ADDED-note label. With
#: the length gate applied first, the classifier missed the single finding it exists to catch.
_STRONG_NOTE_TOKENS = ("注記", "注意")

#: The English equivalent, as a whole word. `ZONE_ANCHORS["notes"]` carries `"note:"` and
#: `"notes:"` with the colon, which is right for growing a box from a heading but misses a
#: note that simply says `NEW NOTE` — the corpus's own ADDED-note label on one templated pair.
#:
#: Word-bounded rather than a substring so it cannot fire on `No.`, which appears in `コードNo.`
#: and `設計訂正書No.` on every sheet. Folding lowercases and NFKC-normalizes first, so the
#: full-width `ＮＯＴＥ` is matched by the same pattern.
_ENGLISH_NOTE_WORD = re.compile(r"\bnotes?\b")

#: A numbered note opens with this: `注１．`, `注1.`. Checked as a prefix rather than a substring
#: so it cannot fire on `発注` or any other word that merely contains the character.
_NOTE_PREFIXES = ("注",)

#: A specification line: heat treatment, hardness, material condition. Both corpus examples
#: carry `施工` and `硬度` together, but either alone is enough to seed — they do not occur in
#: the sibling zones' furniture.
_SPEC_TOKENS = ("施工", "硬度")

#: How far a short neighbour may sit from a seed, as a multiple of the block's own row pitch.
#: The item number `１` sits 12.0 units left of its sentence on a block whose pitch is 9.6
#: (ratio 1.25). 3.0 leaves room without reaching the next column: on the widest corpus block
#: the nearest foreign text is more than 8 pitches away.
COHESION_X_PITCHES = 3.0

#: Longest text admitted by cohesion alone. Cohesion exists to recover item markers — the
#: `１` / `1` / `a` / `b` / `c` / `d` that number a note from just left of it — and every one of
#: those measured on the corpus is 1-2 characters. Anything longer that still is not a note by
#: its own content is something else sharing a row: `追加 3-M8`, a drawing callout, was claimed
#: for `notes_section` on `M7452A0N01-ref-mut000` for exactly that reason. A note long enough to
#: say something does not need cohesion — it seeds on its own.
COHESION_MAX_LEN = 2

#: Two texts are on the same row when their y differs by less than this fraction of the pitch.
#: The item number is at exactly the same y as its sentence, so this only has to absorb
#: baseline jitter, and it must stay well under 1.0 or a neighbour row would qualify.
COHESION_ROW_FRACTION = 0.3

#: Used when a block has a single seed row and therefore no measurable pitch. Relative measures
#: are preferred everywhere here because the two exporters differ ~3x in coordinate scale, so a
#: fixed distance that works on one side is meaningless on the other.
_FALLBACK_PITCH_FRACTION = 0.02


def _fold(text: str) -> str:
    """NFKC + lowercase + whitespace-collapsed, matching the folding used elsewhere.

    NFKC is what makes the full-width and half-width spellings of the same note compare equal —
    the two sides of a comparison come from different exporters and one of them writes
    `４ロール：１２`.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "").strip().lower())


#: How many characters may trail an instruction ending and still leave it an instruction.
#: A note does not stop being one because a revision appended to it — `指示なき角部は糸面取りの
#: こと` becomes `…のこと2` in the corpus's CHANGED label, and an exact `endswith` scored that as
#: not-a-note on the revision side only, i.e. asymmetrically, which is the failure this whole
#: module exists to remove. Bounded at 3 so it cannot reach back into an unrelated clause.
INSTRUCTION_TRAILING_SLACK = 3


def _ends_instruction(raw: str) -> bool:
    """Whether `raw` closes with a work-instruction form, allowing a short trailing edit."""
    tail = raw.rstrip()
    return any(
        token in tail[-(len(token) + INSTRUCTION_TRAILING_SLACK):]
        for token in _INSTRUCTION_ENDINGS
    )


def is_note_sentence(text: str) -> bool:
    """Whether `text` alone looks like a note — no position, no neighbours.

    Deliberately conservative: this only has to catch the lines that *seed* a block. Item
    numbers and short callouts are admitted afterwards by `cohere`, which is where their
    evidence actually is.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    folded = _fold(raw)
    # Strong markers first, BEFORE the length gate — see _STRONG_NOTE_TOKENS.
    if (
        any(tok in raw for tok in _STRONG_NOTE_TOKENS)
        or raw.startswith(_NOTE_PREFIXES)
        or _ENGLISH_NOTE_WORD.search(folded)
    ):
        return True
    if len(raw) < NOTE_SEED_MIN_LEN:
        return False
    if _ends_instruction(raw) or any(tok in raw for tok in _SPEC_TOKENS):
        return True
    # The zone anchors are reused rather than forked: that list carries two hard-won exclusions
    # (`仕上げ` removed for matching `仕上げ記号`; `ロール` measured and rejected) and a fork would
    # silently lose them the next time it is edited.
    return any(_fold(a) in folded for a in ZONE_ANCHORS.get("notes", ()))


def _pitch(ys: Sequence[float], span: float) -> float:
    """The block's own row spacing, from the gaps between distinct seed rows."""
    rows = sorted({round(y, 3) for y in ys})
    gaps = [b - a for a, b in zip(rows, rows[1:], strict=False) if b - a > 0]
    if gaps:
        return sorted(gaps)[len(gaps) // 2]
    return max(span * _FALLBACK_PITCH_FRACTION, 1e-6)


def classify_notes(
    items: Iterable[tuple[str, float, float]],
    regions: Optional[dict],
    *,
    sheet_span: float = 0.0,
) -> list[int]:
    """Indices of `items` that are notes. `items` are `(text, x, y)` in absolute CAD units.

    Two stages:

    1. Seed. Every item that reads as a note on its own content AND is not owned by a zone
       that outranks `notes`. The veto is what separates a real note from the tolerance block's
       `必要な場合は、粗さ区分を記入のこと`, which no content rule can.
    2. Cohere. Short items on the same row as a seed and within `COHESION_X_PITCHES` of the
       seed block horizontally — the item numbers. They are subject to the same ownership veto,
       so a `1` inside the BOM stays the BOM's.

    Returns indices, not entities, so the caller keeps whatever object it started with.
    """
    rows = list(items)
    if not rows:
        return []

    def vetoed(x: float, y: float) -> bool:
        return is_owned_by_other(x, y, regions, "notes")

    seeds = [
        i
        for i, (text, x, y) in enumerate(rows)
        if is_note_sentence(text) and not vetoed(x, y)
    ]
    if not seeds:
        return []

    seed_xs = [rows[i][1] for i in seeds]
    seed_ys = [rows[i][2] for i in seeds]
    span = sheet_span or (max(seed_xs) - min(seed_xs)) or 1.0
    pitch = _pitch(seed_ys, span)
    row_tol = pitch * COHESION_ROW_FRACTION
    x_tol = COHESION_X_PITCHES * pitch

    # Cohesion is measured against ONE seed, never against the seed set's bounding window.
    #
    # The window was written first and leaked badly: a note may legitimately sit far from the
    # block — on `M7452A0N01-rev-mut005` the added `追加注記` is at x=264 while the block is at
    # x=55 — and a window spanning both then admits anything that merely shares a row with any
    # seed anywhere across the sheet. That pulled in the view label `Ａ` and the chamfer callout
    # `Ｃ１`, two of the three false positives left at the time. Requiring a single seed to be
    # near in BOTH axes keeps a distant seed from widening the block it is not part of.
    claimed = set(seeds)
    for i, (text, x, y) in enumerate(rows):
        stripped = (text or "").strip()
        if i in claimed or not stripped or len(stripped) > COHESION_MAX_LEN:
            continue
        near = any(
            abs(y - rows[s][2]) <= row_tol and abs(x - rows[s][1]) <= x_tol
            for s in seeds
        )
        if not near or vetoed(x, y):
            continue
        claimed.add(i)

    return sorted(claimed)
