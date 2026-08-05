"""Match predicted findings to expected ones and count — Stage 0d.

This is where recall comes from, and recall has never existed in this project. Everything
above it on the ladder is defined by optimising against a number that starts here.

## Two rules that decide whether the numbers mean anything

**A prediction is a candidate whose status is not `MATCHED`.**
`generate_deterministic_candidates` returns every checklist row, including items it checked
and found unchanged — a null pair comes back with 50 candidates and 0 discrepancies. A
scorer that counted candidates would report precision near zero on a perfect run.

**Matching must not require the categories to agree.** Category attribution is scored
*separately* from detection, so a finding the engine located but filed under the wrong
category is a category error, not a miss. Requiring category equality to match would
double-count it as both a false negative and a false positive and make the two metrics
impossible to read apart.

## Matching is handle-first, and mostly cannot be

The plan's design was handle-first with spatial and text as fallback. In practice, on these
drawings, the fallback is the common path — for two independent reasons:

  * Expected findings frequently carry a **payload address** (`REF#412`) rather than a DXF
    handle, because entities exploded out of a block have no handle at all. See
    [[Gotcha - Exploded Block Children Have No Handle]]. Predictions never emit payload
    addresses, so such a label can never match on handle.
  * Predictions themselves often carry no `entity_id`: every `bill_of_materials` finding is
    table-derived, and most `title_block` findings come from OCR-corroborated fields.

So the tiers run handle → text → spatial, greedily, each prediction consumed once, and the
report states **how many matches came from each tier**. A result resting mostly on spatial
matching deserves less trust than one resting on handles, and hiding that behind a single F1
would be the easiest way to ship a wrong number confidently.

## This scorer is itself a differ, and can be wrong

The staged plan names that as a risk and requires its decisions be hand-audited on two pairs
before any aggregate is trusted. `PairScore.explain()` exists for exactly that.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..audit.comparison.reconciler import MATCH_RADIUS_MM
from ..audit.comparison.spatial_differ import SpatialDiffer
from ..audit.comparison.taxonomy import TAXONOMY
from .corpus import CorpusPair, ExpectedFinding

# Matched by text when the normalised strings are equal. Deliberately equality rather than a
# similarity threshold: a threshold here would be a seventeenth hand-guessed constant, and
# Stage 0.5's whole point is that the sixteen existing ones were never measured.
CATEGORIES: tuple[str, ...] = tuple(TAXONOMY.keys())

MATCH_TIERS = ("handle", "text", "spatial")


def _normalize(text: str | None) -> str:
    """The engine's own normaliser, so labels and scoring share one definition of sameness.

    The annotation guideline requires this: `SpatialDiffer._normalize_text` is what decides
    that `Ｃ１` and `C1`, or `22.7` and `22.70`, are the same text. Reimplementing it here
    would let the corpus and the engine drift apart on the meaning of "changed".
    """
    return SpatialDiffer._normalize_text(str(text or ""))


@dataclass(frozen=True)
class Prediction:
    """One discrepancy an engine reported, reduced to what the scorer matches on."""

    category: str
    status: str
    handle: str | None
    new_text: str
    old_text: str
    coordinates: tuple[float, float] | None

    @property
    def texts(self) -> set[str]:
        return {t for t in (_normalize(self.new_text), _normalize(self.old_text)) if t}

    @classmethod
    def from_candidate(cls, candidate: Any) -> Prediction:
        coords = getattr(candidate, "coordinates", None) or getattr(
            candidate, "ref_coordinates", None
        )
        point = (
            (float(coords[0]), float(coords[1]))
            if coords and len(coords) >= 2
            else None
        )
        return cls(
            category=str(getattr(candidate, "category", "") or ""),
            status=str(getattr(candidate, "status", "") or ""),
            handle=(getattr(candidate, "entity_id", None) or None),
            new_text=str(getattr(candidate, "text_content", "") or ""),
            # REMOVED findings put the old value in `text_content` and leave
            # `original_value` None, so both fields are read on both sides rather than
            # assuming a fixed old/new split.
            old_text=str(getattr(candidate, "original_value", "") or ""),
            coordinates=point,
        )


@dataclass(frozen=True)
class ExpectedContext:
    """An expected finding resolved against the payloads it addresses.

    A label carrying `REF#412` names a line in the entity payload, not a handle a
    prediction could ever cite. Resolving it here is what gives the text and the position
    that the fallback tiers match on.
    """

    finding: ExpectedFinding
    texts: set[str]
    coordinates: tuple[float, float] | None
    resolved: bool

    @classmethod
    def build(
        cls,
        finding: ExpectedFinding,
        ref_entities: list[Any],
        rev_entities: list[Any],
    ) -> ExpectedContext:
        from ..audit.bom.zone_detector import entity_anchor

        entity = finding.resolve(ref_entities, rev_entities)
        texts = {t for t in (_normalize(finding.ref_text), _normalize(finding.rev_text)) if t}
        point: tuple[float, float] | None = None
        if entity is not None:
            entity_text = _normalize((getattr(entity, "properties", None) or {}).get("text"))
            if entity_text:
                texts.add(entity_text)
            anchor = entity_anchor(entity)
            if anchor and len(anchor) >= 2:
                point = (float(anchor[0]), float(anchor[1]))
        return cls(finding=finding, texts=texts, coordinates=point, resolved=entity is not None)


@dataclass
class Match:
    expected: ExpectedContext
    prediction: Prediction
    tier: str

    @property
    def status_agrees(self) -> bool:
        return self.expected.finding.status == self.prediction.status

    @property
    def category_agrees(self) -> bool:
        return self.expected.finding.category == self.prediction.category


@dataclass
class PairScore:
    pair_id: str
    provenance: str
    matches: list[Match] = field(default_factory=list)
    missed: list[ExpectedContext] = field(default_factory=list)
    spurious: list[Prediction] = field(default_factory=list)
    duplicates: list[Prediction] = field(default_factory=list)
    unresolvable: list[ExpectedFinding] = field(default_factory=list)

    @property
    def expected_count(self) -> int:
        return len(self.matches) + len(self.missed)

    @property
    def is_zero_finding(self) -> bool:
        """Ground truth is 'no findings' — a pure precision probe.

        Recall is undefined on these (the denominator is zero), so they are aggregated
        separately rather than being allowed to silently inflate a recall figure.
        """
        return self.expected_count == 0

    def explain(self) -> str:
        """Every decision this scorer made on one pair, for hand-auditing.

        The staged plan requires two pairs be audited this way before any aggregate is
        trusted, because the matcher is a differ and can be wrong in the same ways the
        engine can.
        """
        lines = [f"# {self.pair_id} ({self.provenance})", ""]
        for match in self.matches:
            finding = match.expected.finding
            flags = []
            if not match.status_agrees:
                flags.append(f"status {finding.status}->{match.prediction.status}")
            if not match.category_agrees:
                flags.append(f"category {finding.category}->{match.prediction.category}")
            note = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(
                f"  MATCH   ({match.tier:7}) {finding.qualified_handle:12} "
                f"{finding.status:8} {_first(match.expected.texts)!r}{note}"
            )
        for miss in self.missed:
            resolved = "" if miss.resolved else "  [label does not resolve to any entity]"
            lines.append(
                f"  MISS              {miss.finding.qualified_handle:12} "
                f"{miss.finding.status:8} {_first(miss.texts)!r}{resolved}"
            )
        for extra in self.spurious:
            lines.append(
                f"  SPURIOUS          {str(extra.handle or '-'):12} "
                f"{extra.status:8} {_first(extra.texts)!r} [{extra.category}]"
            )
        for dup in self.duplicates:
            lines.append(
                f"  DUPLICATE         {str(dup.handle or '-'):12} "
                f"{dup.status:8} {_first(dup.texts)!r}"
            )
        return "\n".join(lines)


def _first(texts: Iterable[str]) -> str:
    return next(iter(sorted(texts)), "")


# ── matching ──────────────────────────────────────────────────────────────────────────


def _distance(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    return math.hypot(a[0] - b[0], a[1] - b[1])


def score_pair(
    pair: CorpusPair,
    predictions: list[Prediction],
    ref_entities: list[Any],
    rev_entities: list[Any],
) -> PairScore:
    """Greedy handle → text → spatial matching, each prediction consumed at most once."""
    score = PairScore(pair_id=pair.pair_id, provenance=pair.provenance)
    findings = pair.labels.findings if pair.labels else []

    contexts: list[ExpectedContext] = []
    for finding in findings:
        context = ExpectedContext.build(finding, ref_entities, rev_entities)
        if not context.resolved:
            # A label pointing at no entity is a corpus defect, not a detection failure.
            # Counting it as a miss would blame the engine for the corpus being wrong.
            score.unresolvable.append(finding)
        contexts.append(context)

    remaining = list(range(len(predictions)))
    unmatched = list(contexts)

    for tier in MATCH_TIERS:
        still_unmatched: list[ExpectedContext] = []
        for context in unmatched:
            index = _best_prediction(tier, context, predictions, remaining)
            if index is None:
                still_unmatched.append(context)
                continue
            remaining.remove(index)
            score.matches.append(Match(context, predictions[index], tier))
        unmatched = still_unmatched

    score.missed = [c for c in unmatched if c.resolved]
    # Unresolvable labels are excluded from `missed` too — see above. They are reported on
    # their own line so a corpus defect is never quietly absorbed into a recall figure.

    matched_contexts = {id(m.expected): m for m in score.matches}
    for index in remaining:
        prediction = predictions[index]
        if _would_match_any(prediction, matched_contexts.values()):
            # A second prediction for an expected finding already matched: the duplicate
            # bug class (cache v13/v16), counted separately from an outright false positive
            # because it is a different defect with a different fix.
            score.duplicates.append(prediction)
        else:
            score.spurious.append(prediction)
    return score


def _viable(
    tier: str,
    context: ExpectedContext,
    predictions: list[Prediction],
    available: list[int],
) -> list[tuple[int, float]]:
    """Every prediction this tier considers a possible match, with a distance where one
    is meaningful (0.0 for the non-spatial tiers)."""
    if tier == "handle":
        if context.finding.anchor_kind != "handle":
            return []  # a payload address is unaddressable by any prediction
        wanted = context.finding.qualified_handle
        return [
            (i, 0.0) for i in available if predictions[i].handle and predictions[i].handle == wanted
        ]

    if tier == "text":
        if not context.texts:
            return []
        return [(i, 0.0) for i in available if context.texts & predictions[i].texts]

    viable = []
    for index in available:
        distance = _distance(context.coordinates, predictions[index].coordinates)
        if distance is not None and distance <= MATCH_RADIUS_MM:
            viable.append((index, distance))
    return viable


def _best_prediction(
    tier: str,
    context: ExpectedContext,
    predictions: list[Prediction],
    available: list[int],
) -> int | None:
    """The best available prediction for one expected finding, under one tier's rule.

    Category is a *preference*, not a filter. Both extremes are wrong:

      * **Requiring** category equality would turn every category error into a miss plus a
        false positive, double-counting it and making attribution impossible to read.
      * **Ignoring** category lets short normalised strings collide across the sheet. That
        is not hypothetical — the first audited pair matched an expected `bill_of_materials`
        cell `a` against a `drawing_views` prediction `Ａ` (fullwidth, NFKC-folds to `a`)
        while the genuine BOM predictions were binned as duplicates. Precision and recall
        were both wrong, in opposite directions, on the same pair.

    So candidates are ranked: same category first, then same status, then nearest.
    """
    viable = _viable(tier, context, predictions, available)
    if not viable:
        return None
    finding = context.finding
    viable.sort(
        key=lambda item: (
            predictions[item[0]].category != finding.category,
            predictions[item[0]].status != finding.status,
            item[1],
        )
    )
    return viable[0][0]


def _would_match_any(prediction: Prediction, matches: Iterable[Match]) -> bool:
    """Whether an unmatched prediction is a second report of an already-matched finding.

    Deliberately narrow — same category, and the *same* handle or the *same* text. Two
    things it used to allow, and no longer does:

      * **Cross-category.** An unrelated false positive sharing a short string got absolved
        as a duplicate, and precision read too high.
      * **Mere proximity.** A different string nearby in the same category is a *different*
        finding; if ground truth does not have it, it is a false positive. Allowing it made
        the duplicate/spurious split depend on whether a candidate happened to carry
        coordinates at all — BOM findings mostly do not — which is noise, not a measurement.

    The case that forced this: the engine reports one edited BOM row as five cell-level
    findings, against a guideline that says one row is one finding. Four of those five are
    over-reporting and count against precision. Calling some of them "duplicates" on the
    strength of a coincidental coordinate would have quietly forgiven them.
    """
    for match in matches:
        if prediction.category != match.expected.finding.category:
            continue
        if prediction.handle and prediction.handle == match.expected.finding.qualified_handle:
            return True
        if match.expected.texts & prediction.texts:
            return True
    return False


# ── aggregation ───────────────────────────────────────────────────────────────────────


@dataclass
class CorpusScore:
    pair_scores: list[PairScore] = field(default_factory=list)

    @property
    def scored(self) -> list[PairScore]:
        """Pairs with at least one expected finding — the only ones recall is defined on."""
        return [p for p in self.pair_scores if not p.is_zero_finding]

    @property
    def zero_finding(self) -> list[PairScore]:
        return [p for p in self.pair_scores if p.is_zero_finding]

    def counts(self, category: str | None = None) -> dict[str, int]:
        """True positives, false negatives and false positives, optionally per category.

        A match is attributed to its **expected** category, and a spurious prediction to
        its own — so a category error shows up as neither a miss nor a false positive
        overall, only in the attribution accuracy below.
        """
        tp = fn = fp = dup = 0
        for pair in self.scored:
            tp += sum(
                1
                for m in pair.matches
                if category is None or m.expected.finding.category == category
            )
            fn += sum(
                1 for c in pair.missed if category is None or c.finding.category == category
            )
            fp += sum(1 for p in pair.spurious if category is None or p.category == category)
            dup += sum(1 for p in pair.duplicates if category is None or p.category == category)
        return {"tp": tp, "fn": fn, "fp": fp, "duplicates": dup}

    def metrics(self, category: str | None = None) -> dict[str, Any]:
        c = self.counts(category)
        tp, fn, fp = c["tp"], c["fn"], c["fp"]
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall and (precision + recall)
            else (0.0 if precision is not None and recall is not None else None)
        )
        return {**c, "precision": precision, "recall": recall, "f1": f1}

    def macro_f1(self) -> float | None:
        scores = [
            self.metrics(category)["f1"]
            for category in CATEGORIES
            if self.counts(category)["tp"] + self.counts(category)["fn"] > 0
        ]
        scores = [s for s in scores if s is not None]
        return sum(scores) / len(scores) if scores else None

    def status_confusion(self) -> Counter:
        """(expected, predicted) status pairs over matched findings.

        Found-but-mis-statused is a downgrade, not a miss — reported here so it never
        hides inside recall.
        """
        return Counter(
            (m.expected.finding.status, m.prediction.status)
            for pair in self.scored
            for m in pair.matches
        )

    def category_attribution(self) -> dict[str, Any]:
        matches = [m for pair in self.scored for m in pair.matches]
        correct = sum(1 for m in matches if m.category_agrees)
        return {
            "matched": len(matches),
            "correct": correct,
            "accuracy": correct / len(matches) if matches else None,
            "confusion": Counter(
                (m.expected.finding.category, m.prediction.category)
                for m in matches
                if not m.category_agrees
            ),
        }

    def tier_breakdown(self) -> Counter:
        return Counter(m.tier for pair in self.scored for m in pair.matches)

    def zero_finding_false_positives(self) -> int:
        """Every finding reported on a zero-finding pair. The purest precision signal."""
        return sum(len(p.spurious) + len(p.duplicates) for p in self.zero_finding)

    def unresolvable_labels(self) -> list[str]:
        return [
            f"{pair.pair_id}:{finding.qualified_handle}"
            for pair in self.pair_scores
            for finding in pair.unresolvable
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairs": len(self.pair_scores),
            "scored_pairs": len(self.scored),
            "zero_finding_pairs": len(self.zero_finding),
            "zero_finding_false_positives": self.zero_finding_false_positives(),
            "micro": self.metrics(),
            "macro_f1": self.macro_f1(),
            "per_category": {c: self.metrics(c) for c in CATEGORIES},
            "status_confusion": {f"{a}->{b}": n for (a, b), n in self.status_confusion().items()},
            "category_attribution": {
                k: (dict(v) if isinstance(v, Counter) else v)
                for k, v in self.category_attribution().items()
                if k != "confusion"
            }
            | {
                "confusion": {
                    f"{a}->{b}": n for (a, b), n in self.category_attribution()["confusion"].items()
                }
            },
            "match_tiers": dict(self.tier_breakdown()),
            "unresolvable_labels": self.unresolvable_labels(),
        }


def _rate(value: float | None, tp: int, total: int) -> str:
    """A rate always printed with the counts behind it.

    At this corpus size every rate is a small fraction of a small number. Printing `0.86`
    alone invites a confidence the sample cannot support; printing `0.86 (6/7)` does not.
    """
    if value is None:
        return "    n/a (0/0)"
    return f"{value:8.2f} ({tp}/{total})"


def format_report(score: CorpusScore) -> str:
    lines: list[str] = []
    micro = score.metrics()
    total_expected = micro["tp"] + micro["fn"]

    lines.append("=" * 78)
    lines.append("Comparison engine evaluation")
    lines.append("=" * 78)
    lines.append("")
    lines.append(
        f"  {len(score.pair_scores)} pair(s): {len(score.scored)} with expected findings, "
        f"{len(score.zero_finding)} zero-finding (precision probes)"
    )
    lines.append("")
    lines.append("  ZERO-FINDING PAIRS — ground truth is no findings at all")
    lines.append(
        f"    false positives: {score.zero_finding_false_positives()} "
        f"across {len(score.zero_finding)} pair(s)"
    )
    lines.append("")
    lines.append("  DETECTION (over pairs that expect findings)")
    predicted = micro["tp"] + micro["fp"]
    lines.append(f"    precision {_rate(micro['precision'], micro['tp'], predicted)}")
    lines.append(f"    recall    {_rate(micro['recall'], micro['tp'], total_expected)}")
    lines.append(
        f"    F1        {micro['f1']:8.2f}" if micro["f1"] is not None else "    F1           n/a"
    )
    macro = score.macro_f1()
    lines.append(f"    macro F1  {macro:8.2f}" if macro is not None else "    macro F1     n/a")
    lines.append(f"    duplicates: {micro['duplicates']}")
    lines.append("")
    lines.append("  PER CATEGORY")
    lines.append(f"    {'category':30} {'precision':>18} {'recall':>18} {'F1':>6}")
    for category in CATEGORIES:
        m = score.metrics(category)
        expected = m["tp"] + m["fn"]
        if expected == 0 and m["fp"] == 0:
            continue
        f1 = f"{m['f1']:6.2f}" if m["f1"] is not None else "   n/a"
        lines.append(
            f"    {category:30} {_rate(m['precision'], m['tp'], m['tp'] + m['fp']):>18} "
            f"{_rate(m['recall'], m['tp'], expected):>18} {f1}"
        )
    lines.append("")

    tiers = score.tier_breakdown()
    lines.append("  HOW MATCHES WERE MADE")
    for tier in MATCH_TIERS:
        lines.append(f"    {tier:10} {tiers.get(tier, 0)}")
    lines.append(
        "    (handle matching is the trustworthy tier; a result resting on spatial "
        "matching is weaker)"
    )
    lines.append("")

    attribution = score.category_attribution()
    lines.append("  CATEGORY ATTRIBUTION — scored independently of detection")
    lines.append(
        "    accuracy "
        + _rate(attribution["accuracy"], attribution["correct"], attribution["matched"])
    )
    for (expected, predicted), count in attribution["confusion"].most_common(5):
        lines.append(f"      {expected} -> {predicted}: {count}")
    lines.append("")

    confusion = score.status_confusion()
    downgrades = {k: v for k, v in confusion.items() if k[0] != k[1]}
    lines.append("  STATUS CONFUSION — found but mis-statused is a downgrade, not a miss")
    if downgrades:
        for (expected, predicted), count in sorted(downgrades.items()):
            lines.append(f"    {expected} -> {predicted}: {count}")
    else:
        lines.append("    none")
    lines.append("")

    unresolvable = score.unresolvable_labels()
    if unresolvable:
        lines.append("  CORPUS DEFECTS — labels resolving to no entity, excluded from recall")
        for item in unresolvable[:10]:
            lines.append(f"    {item}")
        lines.append("")

    lines.append("-" * 78)
    lines.append(
        f"  Read with care: {total_expected} expected finding(s) over {len(score.scored)} "
        f"pair(s). Every rate here is a small fraction of a small number and the error bars"
    )
    lines.append(
        "  are wide. Mutation pairs are drawn from the engine's own comparison pool, so"
    )
    lines.append(
        "  they cannot reveal a scoping bug, and their category attribution is not"
    )
    lines.append("  independent. Only human-labelled pairs can settle either.")
    lines.append("-" * 78)
    return "\n".join(lines)
