"""Converts an app Manual Check session into an eval-corpus label draft.

## Why this exists

This project grew two ground-truth stores that never met:

* Manual Check (2026-08-18) writes `ground_truth_markings` to Mongo. It is the only path
  with a UI, so it is the one an engineer actually uses.
* The eval corpus reads `tests/fixtures/eval/labels/*.json`. It is the only path
  `tools/eval_corpus.py status` counts, so it is the one that moves Stage 0b and the rung gate.

Work in the first was invisible to the second. Measured 2026-08-20: three sessions, 7 live
markings, and Stage 0b reading 4 / 8 as though none of it existed. An annotator had no way to
tell that the UI they were given does not feed the metric it appears to serve.

`GroundTruthMarking`'s own docstring anticipated this -- *"a corpus-style label wants an address,
a category, a status, both texts and `is_bulk`"* -- so the capture schema is already a superset
of what a label needs. This module is the projection, not a redesign of either side.

## What it deliberately does NOT do

It emits a draft. It never installs one. The output goes to `validate` and `label`, which
already enforce the guideline version and refuse an anonymous annotator. A conversion is a
*proposal*: the mapping below is lossy in ways only a person can adjudicate, and a corpus that
can be appended to by a script is a corpus whose provenance is no longer "a human said so".

## The mapping, and where it loses information

| Marking status | Corpus | Why |
| :--- | :--- | :--- |
| `ADDED` | finding `ADDED`, anchored on `rev_address` | |
| `REMOVED` | finding `REMOVED`, anchored on `ref_address` | a removal only exists on the reference |
| `CHANGED` | finding `CHANGED`, anchored on `rev_address` | matches `ExpectedFinding.default_side` |
| `MATCHED` | `not_findings` | `VALID_STATUSES` is `{ADDED, REMOVED, CHANGED}`; a verified non-change is not a finding, but recording it is what makes a false positive there *attributable* rather than merely counted |
| `NOT_A_FINDING` | `not_findings` | exactly the corpus's own definition of one |
| `retracted_at` set | dropped | a retraction is the engineer withdrawing the statement |

The retraction rule is not a detail: of the 38 markings in the session that prompted this, 31
are retracted. A converter that ignored `retracted_at` would have manufactured 31 findings the
engineer had explicitly taken back.

WARNING: `category_source` has nowhere to go. `GroundTruthMarking` records whether a human
chose the category or it was derived from the entity's zone, and says why that matters: the
mutation corpus's attribution figure is a known tautology because its labels come from
`zone_detector`, and the human pairs were *the first non-tautological attribution numbers in
this project* -- which holds only while the engineer's category is independent of the detector.
`ExpectedFinding` has no field for it. So a zone-derived category is tagged `[category:zone]` in
the finding's `notes` and counted separately in `BridgeResult`, rather than being silently
folded in where nothing downstream could ever tell the two apart. That is a mitigation, not a
fix -- the honest fix is a field on `ExpectedFinding`, which is a corpus schema change and not
this module's call to make.

## Addresses are re-resolved, never copied

A marking stores a `handle`; a label needs an address that resolves *inside the frozen payload*.
Those are not the same claim. So every marking is re-resolved against the pair's payload
entities through `ground_truth.address_resolver` -- the same tiered resolver the app uses,
called rather than reimplemented, because a second opinion about which entity a human meant
would be invisible: a mis-resolved label reads perfectly and silently attributes a person's
judgement to the wrong entity. Anything the resolver declines to match is reported as unresolved
and excluded, never guessed at.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ...domain.models.ground_truth import EntityAddress
from ..ground_truth.address_resolver import MatchTier, resolve
from .corpus import GUIDELINE_VERSION, ExpectedFinding, NonFinding, PairLabels

#: Marking statuses that become corpus findings, mapped to the side their address lives on.
#: `CHANGED` anchors on the revision to match `ExpectedFinding.default_side`.
FINDING_STATUS_SIDE: dict[str, str] = {"ADDED": "rev", "REMOVED": "ref", "CHANGED": "rev"}

#: Statuses with no corpus finding equivalent, and what to record them as instead.
NON_FINDING_REASONS: dict[str, str] = {
    "MATCHED": "engineer verified this as unchanged",
    "NOT_A_FINDING": "engineer marked this as deliberately not a finding",
}


@dataclass(frozen=True)
class Unresolved:
    """A live marking that could not be turned into a label, and why.

    Reported rather than dropped quietly: the count of these is the difference between "your
    38 markings became 38 labels" and the truth, and an annotator has no other way to see it.
    """

    marking_id: str
    status: str
    category: str
    reason: str
    text: str = ""


@dataclass
class BridgeResult:
    labels: PairLabels
    unresolved: list[Unresolved] = field(default_factory=list)
    #: How each converted marking resolved, by `MatchTier`. Makes "how far do handles actually
    #: carry us" measurable here too, not just in the app.
    tier_counts: dict[str, int] = field(default_factory=dict)
    retracted_skipped: int = 0
    zone_derived: int = 0

    @property
    def converted(self) -> int:
        return len(self.labels.findings) + len(self.labels.not_findings)


def check_session_matches_pair(
    pair: Any,
    *,
    ref_drawing_id: str,
    rev_drawing_id: str,
    ref_file_hash: str = "",
    rev_file_hash: str = "",
) -> tuple[list[str], list[str]]:
    """`(problems, notes)`. Empty problems means this session describes this pair.

    Checked because the failure it prevents is unrecoverable in practice: labels attached to
    the wrong pair resolve against the wrong payload, produce plausible findings, and get
    committed as ground truth.

    WARNING: Identity is the file hash, not the drawing id. Comparing ids was the obvious
    rule and it is wrong: measured 2026-08-20, the manual-check session for `M745230A01` names
    drawings `6a829d45` / `6a829dd1` while the corpus pair was exported from `6a72ecba` /
    `6a72ecd0` -- and all four file hashes match pairwise. The same sheet uploaded twice gets a
    new `DrawingDocument` each time, so an id check refuses exactly the case this bridge exists
    to serve. `EntityAddress.source_file_hash` already states the principle: the hash "proves
    the drawing is still the same drawing even when every entity id has changed".

    A differing id with a matching hash is therefore a *note*, not a problem. Ids are still
    compared when a hash is unavailable, because a weaker check beats none.

    A session whose sides are swapped relative to the pair is reported as such rather than as a
    generic mismatch -- it is the one wrong-pairing a person is most likely to create by hand,
    and the one whose findings would look most nearly plausible.
    """
    problems: list[str] = []
    notes: list[str] = []
    for side, session_id, session_hash in (
        ("ref", ref_drawing_id, ref_file_hash),
        ("rev", rev_drawing_id, rev_file_hash),
    ):
        meta = getattr(pair, side)
        other = getattr(pair, "rev" if side == "ref" else "ref")
        if session_hash and meta.file_hash:
            if session_hash == meta.file_hash:
                if session_id != meta.drawing_id:
                    notes.append(
                        f"{side}: same file ({meta.file_name}), different upload — "
                        f"pair {meta.drawing_id}, session {session_id}"
                    )
                continue
            if session_hash == other.file_hash:
                problems.append(
                    f"{side}: the session's {side} side is the pair's "
                    f"{'rev' if side == 'ref' else 'ref'} drawing — this session's sides are "
                    f"swapped relative to the pair"
                )
            else:
                problems.append(
                    f"{side}: different file — pair {meta.file_name} "
                    f"({meta.file_hash[:12]}…), session ({session_hash[:12]}…)"
                )
            continue
        if session_id != meta.drawing_id:
            problems.append(
                f"{side}: pair has drawing {meta.drawing_id} ({meta.file_name}), session has "
                f"{session_id}, and no file hash was available to compare them"
            )
    return problems, notes


def _address_of(marking: dict[str, Any], side: str) -> EntityAddress | None:
    raw = marking.get(f"{side}_address")
    if not isinstance(raw, dict):
        return None
    try:
        return EntityAddress.model_validate(raw)
    except Exception:  # noqa: BLE001 - a malformed address is an unresolved marking, not a crash
        return None


def _payload_address(
    address: EntityAddress, side: str, entities: Sequence[Any]
) -> tuple[str | None, MatchTier]:
    """`("REV-1B2A" | "REV#412", tier)` for the payload entity this address names.

    The handle is taken from the resolved entity, not from the address, so the emitted
    label is guaranteed to point at something inside the frozen payload. Copying the stored
    handle would produce an address that reads fine and resolves to nothing -- a corpus defect
    that only `PairLabels.unresolvable` would ever catch, and only if someone ran it.
    """
    resolution = resolve(address, entities)
    if not resolution.ok:
        return None, MatchTier.UNRESOLVED
    prefix = side.upper()[:3]
    handle = getattr(resolution.entity, "handle", None)
    if handle:
        return f"{prefix}-{handle}", resolution.tier
    for index, entity in enumerate(entities):
        if entity is resolution.entity:
            return f"{prefix}#{index}", resolution.tier
    # Resolved to an entity that is not in the list we searched. Not reachable through
    # `resolve`, which only ever returns a member of `entities` -- treated as unresolved rather
    # than trusted, because the alternative is emitting an address for an entity whose payload
    # line we could not name.
    return None, MatchTier.UNRESOLVED


def build_labels(
    *,
    pair_id: str,
    markings: Iterable[dict[str, Any]],
    ref_entities: Sequence[Any],
    rev_entities: Sequence[Any],
    annotator: str,
    annotated_at: str,
    notes: str = "",
) -> BridgeResult:
    """Project live manual-check markings onto a corpus label set.

    `markings` are raw documents as stored -- the shape is pinned by
    `domain/models/ground_truth.py`, and taking dicts keeps this function free of Beanie
    initialisation so it can be tested against literals rather than against a database.
    """
    findings: list[ExpectedFinding] = []
    not_findings: list[NonFinding] = []
    unresolved: list[Unresolved] = []
    tier_counts: dict[str, int] = {}
    retracted = 0
    zone_derived = 0

    for marking in markings:
        marking_id = str(marking.get("_id") or marking.get("id") or "?")
        status = str(marking.get("status") or "").upper()
        category = str(marking.get("category") or "")
        ref_text = str(marking.get("ref_text") or "")
        rev_text = str(marking.get("rev_text") or "")
        note = str(marking.get("notes") or "")

        if marking.get("retracted_at"):
            retracted += 1
            continue

        side = FINDING_STATUS_SIDE.get(status)
        is_finding = side is not None
        if not is_finding and status not in NON_FINDING_REASONS:
            unresolved.append(
                Unresolved(marking_id, status, category, f"unknown marking status {status!r}")
            )
            continue
        # A non-finding is anchored on whichever side it was observed from.
        if side is None:
            side = "rev" if _address_of(marking, "rev") is not None else "ref"

        address = _address_of(marking, side)
        if address is None:
            unresolved.append(
                Unresolved(
                    marking_id,
                    status,
                    category,
                    f"no usable {side}_address on the marking",
                    rev_text or ref_text,
                )
            )
            continue

        entities = rev_entities if side == "rev" else ref_entities
        handle, tier = _payload_address(address, side, entities)
        tier_counts[tier.value] = tier_counts.get(tier.value, 0) + 1
        if handle is None:
            unresolved.append(
                Unresolved(
                    marking_id,
                    status,
                    category,
                    f"{side}_address does not resolve to any entity in the frozen payload",
                    rev_text or ref_text,
                )
            )
            continue

        if not is_finding:
            reason = NON_FINDING_REASONS[status]
            not_findings.append(NonFinding(handle, f"{reason}{f': {note}' if note else ''}"))
            continue

        # `category_source` is not representable on ExpectedFinding -- tag it so a zone-derived
        # category stays distinguishable from a human-chosen one. See the module docstring.
        if str(marking.get("category_source") or "human") == "zone":
            zone_derived += 1
            note = f"[category:zone] {note}".strip()

        try:
            findings.append(
                ExpectedFinding(
                    entity_handle=handle,
                    category=category,
                    status=status,
                    ref_text=ref_text,
                    rev_text=rev_text,
                    notes=note,
                    is_bulk=bool(marking.get("is_bulk", False)),
                )
            )
        except Exception as err:  # noqa: BLE001 - a schema rejection is a reportable miss
            unresolved.append(
                Unresolved(marking_id, status, category, str(err), rev_text or ref_text)
            )

    return BridgeResult(
        labels=PairLabels(
            pair_id=pair_id,
            guideline_version=GUIDELINE_VERSION,
            annotator=annotator,
            annotated_at=annotated_at,
            findings=findings,
            not_findings=not_findings,
            notes=notes,
        ),
        unresolved=unresolved,
        tier_counts=tier_counts,
        retracted_skipped=retracted,
        zone_derived=zone_derived,
    )
