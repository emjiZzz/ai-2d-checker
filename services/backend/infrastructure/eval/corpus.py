"""The evaluation corpus: manifest, labels, integrity, and held-out discipline.

Stage 0b of [[AI Maturity Ladder — Staged Plan]]. The corpus is split across two trees
for confidentiality — entity payloads carry the customer's Japanese text and are the same
class as the source DXFs, which are already gitignored:

| | Location | Contents |
| :--- | :--- | :--- |
| Committed | `tests/fixtures/eval/` | `manifest.json` + hand-authored label files |
| Gitignored | `storage/eval/pairs/` | The entity payloads |

Three rules from `docs/vault/01 - Architecture/Eval Corpus Annotation Guideline.md` are
enforced here in code rather than left to discipline, because each of them fails silently:

1. **Payload drift.** Every payload's sha256 is recorded in the committed manifest and
   checked on load. A quietly edited fixture is the one failure mode that would
   invalidate every historical number at once, retroactively and undetectably.
2. **Held-out pairs.** Three human pairs are touched exactly once, at the end of
   Stage 0.5. `load_corpus()` therefore excludes them by default, and including them
   requires a written reason that is appended to an access log. A held-out pair used for
   tuning is *burned*, and the log is what makes that visible instead of forgotten.
3. **Guideline version.** The guideline says: if a rule changes, re-label every affected
   pair or discard them. Labels record the guideline version they were authored under,
   and loading a label file written under a different version raises rather than silently
   mixing two definitions of "one finding".
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args

from ..audit.comparison.taxonomy import Category
from ..storage.path_resolver import ROOT_DIR, get_storage_root
from .serialize import (
    EvalDrawing,
    EvalEntity,
    canonical_json,
    entities_from_jsonl,
    read_text_stable,
    sha256_text,
    write_text_stable,
)

# Bump when the manifest's own shape changes. Distinct from PAYLOAD_SCHEMA_VERSION: the
# manifest can gain a field without any payload byte moving.
MANIFEST_SCHEMA_VERSION = 1

# Must track the `date:` frontmatter of the annotation guideline. Labels authored under an
# older version are not silently accepted — see rule 3 in the module docstring.
# Bumped when a labelling *rule* changes, because a corpus labelled under two definitions
# cannot be read: you can no longer tell a scoring change from a definition change. A label
# file carrying a different version is rejected rather than migrated — re-label or discard.
#
# 2026-08-06: the guideline's four open questions resolved and it moved to `status: active`.
#   Ruled rows, revision-table rows, amendment/balloon categories, and the bulk threshold all
#   now have rules where they previously had judgement. Safe to bump without re-labelling
#   anything because **zero labels existed** — which is exactly why they were settled first.
GUIDELINE_VERSION = "2026-08-06"

VALID_CATEGORIES: frozenset[str] = frozenset(get_args(Category))
VALID_STATUSES: frozenset[str] = frozenset({"CHANGED", "ADDED", "REMOVED"})

Provenance = Literal["human", "mutation"]
LabelState = Literal["unlabelled", "labelled", "burned"]

# Stage 0b's exit criteria, in one place so `status_report()` and the tests cannot drift
# from the ledger.
REQUIRED_HUMAN_PAIRS = 8
REQUIRED_HELD_OUT = 3
REQUIRED_MUTATION_PAIRS = 30  # Stage 0c; reported here so the gap is visible early.

_SIDES = frozenset({"REF", "REV"})


class CorpusError(RuntimeError):
    """Base for every way the corpus can refuse to load."""


class CorpusDriftError(CorpusError):
    """A payload's bytes no longer match the sha256 recorded in the manifest."""


class CorpusPayloadMissingError(CorpusError):
    """A payload referenced by the manifest is not on disk.

    Expected on a fresh clone — payloads are gitignored by design. Distinct from drift so
    the message can say "export them" instead of "someone edited a fixture".
    """


class LabelSchemaError(CorpusError):
    """A label file is malformed, or was authored under a different guideline version."""


class HeldOutAccessError(CorpusError):
    """Held-out pairs were requested without a recorded reason."""


# ── paths ─────────────────────────────────────────────────────────────────────────────


def default_fixtures_dir() -> Path:
    return Path(os.getenv("EVAL_CORPUS_FIXTURES") or (ROOT_DIR / "tests" / "fixtures" / "eval"))


def default_payload_dir() -> Path:
    return Path(os.getenv("EVAL_CORPUS_PAYLOADS") or (get_storage_root() / "eval" / "pairs"))


def held_out_access_log() -> Path:
    # Derived from the payload dir rather than from the storage root so that pointing
    # EVAL_CORPUS_PAYLOADS at a scratch directory (as the tests do) redirects the log too,
    # instead of appending test noise to the real audit trail.
    return default_payload_dir().parent / "heldout_access.log"


def ocr_cache_dir() -> Path:
    return get_storage_root() / "cache"


# ── labels ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExpectedFinding:
    """One change a human checker would flag. The unit of ground truth.

    `entity_handle` is the address the Stage 0d scorer matches on first — spatial and text
    similarity are the fallback, not the other way round — which is what keeps scoring
    stable while Stage 0.5 moves coordinate thresholds around.

    ## Two address forms, because a DXF handle is not always available

    The annotation guideline assumed every finding could name a DXF handle. Measured over
    the first three exported pairs (3615 entities across 6 drawings), that assumption does
    not hold on this client's drawings:

    | drawing | text entities with a handle |
    | :--- | ---: |
    | M7452A0N01 reference | 2 / 249 (0.8%) |
    | M7452A0N01 revision | 234 / 254 (92.1%) |
    | M745200N01 reference | 25 / 192 (13.0%) |

    The cause is structural and perfectly clean: `handle` and `parent_handle` are mutually
    exclusive across all 3615 entities, with zero exceptions. `DXFParser` explodes every
    INSERT via `ezdxf`'s `virtual_entities()`, which yields *unbound copies carrying no
    handle*; the child is then tagged with the owning INSERT's handle as `parent_handle`
    instead. The reference sheets keep their content inside blocks, so almost nothing on
    them is handle-addressable. REMOVED findings anchor on the reference side, which is
    exactly the side where handles are missing.

    So a label may address its entity either way:

    * `REV-1B2A` — a namespaced DXF handle, preferred when one exists.
    * `REV#412` — line 412 (0-based) of `rev.entities.jsonl`. The payload is frozen by
      sha256 in the committed manifest, so this index is exactly as stable as a handle
      *for this corpus*, and it is available for 100% of entities.

    A payload address is not portable across a re-extraction. That is acceptable because a
    re-extraction changes the payload bytes, which the manifest check catches loudly — the
    corpus cannot silently drift underneath an index. See the vault gotcha
    "Exploded Block Children Have No Handle".
    """

    entity_handle: str
    category: str
    status: str
    ref_text: str = ""
    rev_text: str = ""
    notes: str = ""
    # Set on a bulk addition anchored to a single entity (e.g. a whole view added). The
    # guideline calls these out as easier to score than they look, and requires their
    # counts be reported separately rather than folded into the aggregate.
    is_bulk: bool = False

    def __post_init__(self) -> None:
        if not str(self.entity_handle).strip():
            raise LabelSchemaError(
                "ExpectedFinding.entity_handle is required — it is the scorer's primary "
                "matching key. Use a payload address (REF#412 / REV#412) when the entity "
                "has no DXF handle, which is the normal case for block-exploded content."
            )
        # Validates the address form and raises on a malformed one.
        _ = self.address
        if self.category not in VALID_CATEGORIES:
            raise LabelSchemaError(
                f"Unknown category {self.category!r}. Categories must come from "
                f"taxonomy.py, never be invented. Valid: {sorted(VALID_CATEGORIES)}"
            )
        if self.status not in VALID_STATUSES:
            raise LabelSchemaError(
                f"Unknown status {self.status!r}. Valid: {sorted(VALID_STATUSES)}"
            )

    @property
    def default_side(self) -> str:
        """The side an unprefixed address belongs to.

        Per the guideline: the revision side, except for a REMOVED, which by definition
        only exists on the reference side.
        """
        return "REF" if self.status == "REMOVED" else "REV"

    @property
    def address(self) -> tuple[str, str, str]:
        """`(side, kind, value)` — kind is `"handle"` or `"payload_index"`."""
        raw = str(self.entity_handle).strip()
        side = self.default_side
        # `REV-1B2A` and `REV#412` share a side prefix but not a separator: `-` introduces
        # a handle, `#` a payload line number. The separator is kept on `raw` so the
        # branch below can tell them apart.
        if len(raw) > 3 and raw[:3].upper() in _SIDES and raw[3] in "-#":
            side, raw = raw[:3].upper(), raw[3:]
            if raw.startswith("-"):
                raw = raw[1:]
        if raw.startswith("#"):
            index = raw[1:]
            if not index.isdigit():
                raise LabelSchemaError(
                    f"Malformed payload address {self.entity_handle!r}: expected "
                    f"REF#<line> or REV#<line> with a 0-based line number."
                )
            return side, "payload_index", index
        if not raw:
            raise LabelSchemaError(f"Empty entity address in {self.entity_handle!r}.")
        return side, "handle", raw

    @property
    def anchor_kind(self) -> str:
        return self.address[1]

    @property
    def qualified_handle(self) -> str:
        """The address in canonical namespaced form (`REV-1B2A` or `REV#412`).

        A bare address is ambiguous between the two drawings a comparison holds at once,
        so the side is always made explicit here.
        """
        side, kind, value = self.address
        return f"{side}#{value}" if kind == "payload_index" else f"{side}-{value}"

    def resolve(self, ref_entities: list[Any], rev_entities: list[Any]) -> Any | None:
        """The entity this label points at, or None when the address does not resolve.

        An unresolvable label is a corpus defect, not a scoring miss — the Stage 0d
        scorer should report it as such rather than counting it as a false negative.
        """
        side, kind, value = self.address
        entities = ref_entities if side == "REF" else rev_entities
        if kind == "payload_index":
            index = int(value)
            return entities[index] if 0 <= index < len(entities) else None
        for entity in entities:
            handle = getattr(entity, "handle", None) or (
                getattr(entity, "properties", None) or {}
            ).get("handle")
            if handle and str(handle) == value:
                return entity
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_handle": self.entity_handle,
            "category": self.category,
            "status": self.status,
            "ref_text": self.ref_text,
            "rev_text": self.rev_text,
            "notes": self.notes,
            "is_bulk": self.is_bulk,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExpectedFinding:
        try:
            return cls(
                entity_handle=str(raw["entity_handle"]),
                category=str(raw["category"]),
                status=str(raw["status"]).upper(),
                ref_text=str(raw.get("ref_text") or ""),
                rev_text=str(raw.get("rev_text") or ""),
                notes=str(raw.get("notes") or ""),
                is_bulk=bool(raw.get("is_bulk", False)),
            )
        except KeyError as exc:
            raise LabelSchemaError(f"ExpectedFinding is missing required field {exc}") from exc


@dataclass(frozen=True)
class NonFinding:
    """Something deliberately *not* labelled, and why.

    The guideline asks for these — a pure relocation with identical text, a difference
    inside a safe zone — so that when the engine reports one, the false positive is
    attributable to a decision rather than to an oversight.
    """

    entity_handle: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"entity_handle": self.entity_handle, "reason": self.reason}


@dataclass
class PairLabels:
    pair_id: str
    guideline_version: str
    annotator: str
    annotated_at: str
    findings: list[ExpectedFinding] = field(default_factory=list)
    not_findings: list[NonFinding] = field(default_factory=list)
    notes: str = ""

    @property
    def category_counts(self) -> dict[str, int]:
        counts = {category: 0 for category in sorted(VALID_CATEGORIES)}
        for finding in self.findings:
            counts[finding.category] += 1
        return counts

    @property
    def bulk_count(self) -> int:
        return sum(1 for finding in self.findings if finding.is_bulk)

    @property
    def handle_anchored_count(self) -> int:
        """Labels addressed by a real DXF handle rather than a payload line number.

        Reported rather than assumed: the Stage 0d scorer is handle-first, so this is the
        fraction of the corpus on which handle-first matching actually applies. On this
        client's reference sheets it will be low — see `ExpectedFinding`'s docstring.
        """
        return sum(1 for finding in self.findings if finding.anchor_kind == "handle")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "guideline_version": self.guideline_version,
            "annotator": self.annotator,
            "annotated_at": self.annotated_at,
            "notes": self.notes,
            "findings": [f.to_dict() for f in self.findings],
            "not_findings": [n.to_dict() for n in self.not_findings],
        }

    def unresolvable(self, ref_entities: list[Any], rev_entities: list[Any]) -> list[str]:
        """Addresses that point at no entity in the payloads. A corpus defect."""
        return [
            finding.qualified_handle
            for finding in self.findings
            if finding.resolve(ref_entities, rev_entities) is None
        ]

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, allow_stale_guideline: bool = False) -> PairLabels:
        version = str(raw.get("guideline_version") or "")
        if version != GUIDELINE_VERSION and not allow_stale_guideline:
            raise LabelSchemaError(
                f"Labels for pair {raw.get('pair_id')!r} were authored under annotation "
                f"guideline {version or '<unset>'}, but the current guideline is "
                f"{GUIDELINE_VERSION}. Per the guideline: re-label every affected pair or "
                f"discard them. Mixing two definitions of 'one finding' silently corrupts "
                f"every metric derived from this corpus."
            )
        return cls(
            pair_id=str(raw.get("pair_id") or ""),
            guideline_version=version,
            annotator=str(raw.get("annotator") or ""),
            annotated_at=str(raw.get("annotated_at") or ""),
            findings=[ExpectedFinding.from_dict(f) for f in raw.get("findings") or []],
            not_findings=[
                NonFinding(str(n.get("entity_handle") or ""), str(n.get("reason") or ""))
                for n in raw.get("not_findings") or []
            ],
            notes=str(raw.get("notes") or ""),
        )


# ── pairs ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PairSide:
    """One drawing of a pair: its identity, its payload files, and their digests."""

    drawing_id: str
    file_name: str
    file_hash: str
    drawing_sha256: str
    entities_sha256: str
    entity_count: int
    # The sheet-layout key a hand-aligned zone template would be stored under. Recorded
    # because an offline run cannot resolve one — see `zone_template_risk()`.
    zone_signature: str = ""
    # `EXTRACTION_SCHEMA_VERSION` this side's entities were extracted under, mirrored up from
    # `{side}.drawing.json` so the question "was this pair captured from a stale drawing?" can
    # be answered from the manifest alone, without loading a payload. **0 means unknown** --
    # every pair exported before 2026-08-20 predates the field.
    extraction_schema_version: int = 0
    # Digest of `{side}.ocr.json`, the captured title-block OCR reading. Empty when the
    # drawing had no cached reading at capture time. See `CorpusPair.restore_ocr_cache`.
    ocr_sha256: str = ""
    # The hand-aligned zone template for this sheet, as Y-DOWN fractions. Resolved at load
    # time from the manifest's `zone_templates` map, keyed by `zone_signature` — **not**
    # serialized per side. A zone template is a property of the sheet layout, and every pair
    # in this corpus is the same layout, so storing it per side wrote the identical block 74
    # times and buried the manifest the staged plan requires stay "tiny, reviewable,
    # diffable".
    #
    # Three states, and they are not interchangeable:
    #   None -> never captured. The run falls back to the Mongo lookup, which offline
    #           degrades to plain detection, so the score is not what users see.
    #   {}   -> captured, and this sheet genuinely has no pinned template.
    #   {..} -> captured zones, applied offline exactly as the app applies them.
    #
    # "Captured" is therefore `zone_signature in manifest["zone_templates"]` — one mechanism,
    # no second flag to fall out of step with the map.
    zone_template: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "drawing_id": self.drawing_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "drawing_sha256": self.drawing_sha256,
            "entities_sha256": self.entities_sha256,
            "entity_count": self.entity_count,
            "zone_signature": self.zone_signature,
            "extraction_schema_version": self.extraction_schema_version,
            "ocr_sha256": self.ocr_sha256,
        }

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        zone_templates: dict[str, dict[str, Any]] | None = None,
    ) -> PairSide:
        """`zone_templates` is the manifest-level `{signature: zones}` map.

        Passing `None` (the default) means "no capture information available", which leaves
        `zone_template` as None and sends the engine back to the database. Passing the map —
        even an empty one — is what makes a *missing* signature mean "never captured" and a
        present one mean "captured", including when the captured value is `{}`.
        """
        return cls(
            drawing_id=str(raw.get("drawing_id") or ""),
            file_name=str(raw.get("file_name") or ""),
            file_hash=str(raw.get("file_hash") or ""),
            drawing_sha256=str(raw.get("drawing_sha256") or ""),
            entities_sha256=str(raw.get("entities_sha256") or ""),
            entity_count=int(raw.get("entity_count") or 0),
            zone_signature=str(raw.get("zone_signature") or ""),
            extraction_schema_version=int(raw.get("extraction_schema_version") or 0),
            ocr_sha256=str(raw.get("ocr_sha256") or ""),
            # zone_template is filled in by `load_corpus` from the manifest-level map; a
            # PairSide built straight from a dict is deliberately "never captured".
            zone_template=zone_templates.get(str(raw.get("zone_signature") or ""))
            if zone_templates is not None
            else None,
        )

    def ocr_cache_filename(self) -> str:
        """The title-block OCR cache file this drawing resolves to.

        `generate_deterministic_candidates` is *not* network-free: on an OCR cache miss it
        calls Gemini (`orchestrator.py:464-467`). Recording the expected filename here is
        what makes Stage 0's "zero network calls" criterion checkable rather than assumed.
        The version segment is read from the cache manager so the two cannot drift.
        """
        from ..audit.comparison.cache_manager import ComparisonCacheManager

        version = ComparisonCacheManager.OCR_CACHE_VERSION
        return f"title_block_ocr_{version}_{self.drawing_id}_{self.file_hash}.json"


@dataclass
class CorpusPair:
    pair_id: str
    provenance: str
    held_out: bool
    label_state: str
    ref: PairSide
    rev: PairSide
    labels: PairLabels | None = None
    notes: str = ""
    payload_dir: Path | None = None
    # For a mutation pair: the recipe that regenerates it — base pair, side, seed and the
    # operators drawn. This is what makes generated labels safe to leave untracked: the
    # committed manifest already carries everything needed to reproduce them byte for byte.
    mutation: dict[str, Any] | None = None
    labels_sha256: str = ""

    # -- payload access ---------------------------------------------------

    @property
    def dir(self) -> Path:
        base = self.payload_dir or default_payload_dir()
        return base / self.pair_id

    def _payload_paths(self, side: str) -> tuple[Path, Path]:
        return self.dir / f"{side}.drawing.json", self.dir / f"{side}.entities.jsonl"

    @property
    def generated_labels_path(self) -> Path:
        return self.dir / "labels.json"

    def verify(self) -> None:
        """Raise unless both sides' payloads exist and hash to the manifest's values."""
        for side, meta in (("ref", self.ref), ("rev", self.rev)):
            drawing_path, entities_path = self._payload_paths(side)
            for path, expected, what in (
                (drawing_path, meta.drawing_sha256, "drawing stub"),
                (entities_path, meta.entities_sha256, "entity payload"),
            ):
                if not path.exists():
                    raise CorpusPayloadMissingError(
                        f"{self.pair_id}/{side}: {what} not found at {path}. Payloads are "
                        f"gitignored by design — re-export this pair with "
                        f"`tools/eval_corpus.py export`."
                    )
                actual = sha256_text(read_text_stable(path))
                if actual != expected:
                    raise CorpusDriftError(
                        f"{self.pair_id}/{side}: {what} at {path} has drifted.\n"
                        f"  manifest: {expected}\n"
                        f"  on disk:  {actual}\n"
                        f"Every metric ever recorded against this pair was measured on the "
                        f"manifest's bytes. Restore the payload, or re-export and re-label — "
                        f"do not update the manifest to match."
                    )

    def load(self) -> tuple[EvalDrawing, EvalDrawing, list[EvalEntity], list[EvalEntity]]:
        """Verified payloads, in the argument order `generate_deterministic_candidates`
        takes them: `(ref_drawing, rev_drawing, ref_entities, rev_entities)`."""
        self.verify()
        ref_drawing_path, ref_entities_path = self._payload_paths("ref")
        rev_drawing_path, rev_entities_path = self._payload_paths("rev")
        return (
            EvalDrawing.from_dict(json.loads(read_text_stable(ref_drawing_path))),
            EvalDrawing.from_dict(json.loads(read_text_stable(rev_drawing_path))),
            entities_from_jsonl(read_text_stable(ref_entities_path)),
            entities_from_jsonl(read_text_stable(rev_entities_path)),
        )

    # -- offline readiness ------------------------------------------------

    def ocr_payload_path(self, side: str) -> Path:
        return self.dir / f"{side}.ocr.json"

    def restore_ocr_cache(self, cache_dir: Path | None = None) -> list[str]:
        """Put each side's captured OCR reading into the cache, replacing any other reading.

        **This is what makes a score reproducible.** The title-block reading used to live
        only in `storage/cache/`, outside the sha256-pinned corpus — so deleting old
        comparisons silently removed it, and the engine fell back to spatial title
        extraction on one side while the other still had a cached reading. Nothing failed;
        the numbers just quietly stopped meaning the same thing.

        Restoring rather than injecting because `generate_deterministic_candidates` reads
        the cache internally and offers no seam to pass a reading through. Idempotent: it
        only ever writes back exactly what the corpus captured.

        ⚠ **It writes over a DIFFERING entry, and that is the point.** Until 2026-08-17 the
        write was guarded by `if not target.exists()`, so this filled a *gap* but could not
        repair a *stale* entry — while this docstring claimed it made a score reproducible
        and `run_corpus` claimed it made the score "a function of the corpus alone". Both
        were false whenever `storage/cache/` already held a different reading for the same
        drawing and file hash, which is the normal state on any machine that has run a live
        comparison, because the engine writes that cache itself. Measured: planting a
        `STALE9999` DWG_NO and calling this reported "nothing restored" and left the planted
        value in place.

        The corpus is the authority for a reproducible score, so a differing entry loses.
        Overwrites are reported distinctly (`"<name> (replaced a differing entry)"`) and
        `tools/eval.py` prints them, because silently repairing this would trade one
        invisible state dependency for another. See the vault note "A Fixed OCR Misread
        Came Back Through the Title Zone".
        """
        base = cache_dir or ocr_cache_dir()
        restored: list[str] = []
        for name, side in (("ref", self.ref), ("rev", self.rev)):
            payload = self.ocr_payload_path(name)
            if not payload.exists():
                continue
            text = read_text_stable(payload)
            if side.ocr_sha256 and sha256_text(text) != side.ocr_sha256:
                raise CorpusDriftError(
                    f"{self.pair_id}/{name}: captured OCR reading at {payload} has drifted "
                    f"from the manifest. Every title_block number ever recorded for this "
                    f"pair was measured on the manifest's bytes."
                )
            target = base / side.ocr_cache_filename()
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                write_text_stable(target, text)
                restored.append(target.name)
            else:
                # Compare the READING, not the bytes. **19 corpus pair-sides share this one
                # cache key** — every mutation pair derives from a base drawing and reuses its
                # id and file hash, so `M7452A0N01/ref` and 18 mutation sides all map here —
                # and the same capture exported twice differs in JSON formatting alone.
                # Measured 2026-08-17: every such collision in this corpus is formatting-only,
                # identical after parse. A byte comparison calls all of them stale and rewrites
                # them on every run: 4 pointless writes per run, reported as if something were
                # wrong. Only a differing *reading* is worth replacing.
                try:
                    stale = json.loads(read_text_stable(target)) != json.loads(text)
                except ValueError:
                    stale = True  # unparseable cache entry: the corpus reading wins
                if stale:
                    write_text_stable(target, text)
                    restored.append(f"{target.name} (replaced a differing entry)")
        return restored

    def missing_ocr_cache(self, cache_dir: Path | None = None) -> list[str]:
        """Cache files whose absence would change the title-block comparison.

        A side counts as covered if the reading is in the cache **or** captured in the
        payload, since `restore_ocr_cache()` puts the latter back before a run.
        """
        base = cache_dir or ocr_cache_dir()
        missing = []
        for name, side in (("ref", self.ref), ("rev", self.rev)):
            if (base / side.ocr_cache_filename()).exists():
                continue
            if self.ocr_payload_path(name).exists():
                continue
            missing.append(side.ocr_cache_filename())
        return missing

    def uncaptured_ocr_sides(self) -> list[str]:
        """Sides whose reading is not in the payload — i.e. still borrowed from the cache.

        A pair with these is one `storage/cache/` deletion away from scoring differently.
        """
        return [
            name
            for name, _side in (("ref", self.ref), ("rev", self.rev))
            if not self.ocr_payload_path(name).exists()
        ]

    def zone_template_risk(self) -> list[str]:
        """Sheet signatures whose zone boxes an offline run will not reproduce.

        `extract_dynamic_regions_async` applies hand-aligned zone templates on top of
        detection, resolved from Mongo by sheet signature. An offline run has no Beanie
        session, `resolve_zone_overrides` raises, and the handler degrades to plain
        detection — logged, then carried on. So a pair whose sheet has a pinned template is
        compared against *different zone boxes* offline than in the app, and a baseline
        measured that way is not a baseline of what users see.

        A side that has **captured** its template carries the fractions in the manifest and
        is no longer at risk, including when the capture found no template at all — `{}` is
        an answer, `None` is an unasked question. Run `tools/eval_corpus.py capture-zones`
        to clear a pair. See the vault gotcha "Zone Templates Vanish in Offline Eval".
        """
        return sorted(
            {
                side.zone_signature
                for side in (self.ref, self.rev)
                if side.zone_signature and side.zone_template is None
            }
        )

    def uncaptured_zone_sides(self) -> list[str]:
        """Sides whose zone template is still resolved from the database at run time."""
        return [
            name
            for name, side in (("ref", self.ref), ("rev", self.rev))
            if side.zone_template is None
        ]

    # -- serialization ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "provenance": self.provenance,
            "held_out": self.held_out,
            "label_state": self.label_state,
            "notes": self.notes,
            "ref": self.ref.to_dict(),
            "rev": self.rev.to_dict(),
            "category_counts": self.labels.category_counts if self.labels else {},
            "finding_count": len(self.labels.findings) if self.labels else 0,
        }


@dataclass
class EvalCorpus:
    pairs: list[CorpusPair]
    fixtures_dir: Path
    payload_dir: Path
    held_out_included: bool = False

    def __iter__(self) -> Iterable[CorpusPair]:
        return iter(self.pairs)

    def __len__(self) -> int:
        return len(self.pairs)

    def by_id(self, pair_id: str) -> CorpusPair | None:
        return next((p for p in self.pairs if p.pair_id == pair_id), None)

    @property
    def human(self) -> list[CorpusPair]:
        return [p for p in self.pairs if p.provenance == "human"]

    @property
    def mutation(self) -> list[CorpusPair]:
        return [p for p in self.pairs if p.provenance == "mutation"]

    @property
    def labelled(self) -> list[CorpusPair]:
        return [p for p in self.pairs if p.label_state == "labelled" and p.labels is not None]

    def verify_all(self) -> None:
        for pair in self.pairs:
            pair.verify()

    def status_report(self) -> dict[str, Any]:
        """Progress against Stage 0b's exit criteria, in counts rather than adjectives."""
        # Held-out pairs are counted from the manifest, not from `self.pairs`, so the
        # report stays honest when they have (correctly) been excluded from the load.
        manifest = read_manifest(self.fixtures_dir)
        all_entries = manifest.get("pairs") or []
        held_out_total = sum(1 for entry in all_entries if entry.get("held_out"))
        human = [entry for entry in all_entries if entry.get("provenance") == "human"]
        mutation = [entry for entry in all_entries if entry.get("provenance") == "mutation"]
        # Counted over human pairs only. Mutation pairs are labelled by construction, so
        # folding them in would report "54 / 8 labelled" while zero annotation had happened —
        # a progress bar that fills itself is worse than none.
        labelled_human = sum(1 for entry in human if entry.get("label_state") == "labelled")
        burned = [
            entry.get("pair_id") for entry in all_entries if entry.get("label_state") == "burned"
        ]
        zero_finding = sum(
            1 for entry in mutation if (entry.get("mutation") or {}).get("zero_finding")
        )
        return {
            "human_pairs": len(human),
            "human_pairs_required": REQUIRED_HUMAN_PAIRS,
            "labelled_human_pairs": labelled_human,
            "held_out": held_out_total,
            "held_out_required": REQUIRED_HELD_OUT,
            "mutation_pairs": len(mutation),
            "mutation_pairs_required": REQUIRED_MUTATION_PAIRS,
            "zero_finding_pairs": zero_finding,
            "burned_pairs": burned,
            "stage_0b_complete": (
                len(human) >= REQUIRED_HUMAN_PAIRS
                and labelled_human >= REQUIRED_HUMAN_PAIRS
                and held_out_total >= REQUIRED_HELD_OUT
                and not burned
            ),
            "stage_0c_complete": len(mutation) >= REQUIRED_MUTATION_PAIRS and zero_finding > 0,
        }


# ── manifest I/O ──────────────────────────────────────────────────────────────────────


def manifest_path(fixtures_dir: Path | None = None) -> Path:
    return (fixtures_dir or default_fixtures_dir()) / "manifest.json"


def read_manifest(fixtures_dir: Path | None = None) -> dict[str, Any]:
    path = manifest_path(fixtures_dir)
    if not path.exists():
        raise CorpusError(
            f"No eval manifest at {path}. Create one with `tools/eval_corpus.py init`."
        )
    raw = json.loads(read_text_stable(path))
    version = int(raw.get("schema_version") or 0)
    if version != MANIFEST_SCHEMA_VERSION:
        raise CorpusError(
            f"Manifest at {path} is schema_version {version}; this code reads "
            f"{MANIFEST_SCHEMA_VERSION}."
        )
    return raw


def write_manifest(manifest: dict[str, Any], fixtures_dir: Path | None = None) -> Path:
    path = manifest_path(fixtures_dir)
    # Indented rather than canonical-compact: the manifest is the reviewable half of the
    # corpus and lands in git, so a readable diff matters more than a short file. It is
    # not itself hashed, so the encoding is free to differ from the payloads'.
    text = json.dumps(json.loads(canonical_json(manifest)), ensure_ascii=False, indent=2) + "\n"
    write_text_stable(path, text)
    return path


def empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "guideline_version": GUIDELINE_VERSION,
        "pairs": [],
    }


def _record_held_out_access(reason: str, pair_ids: list[str]) -> None:
    """Append to the access log.

    The guideline: a held-out pair used for tuning is burned, marked in the manifest and
    replaced. That rule is unenforceable if nobody can tell it happened, so every access
    leaves a line here. This is a record, not a permission check.
    """
    path = held_out_access_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"{stamp}\t{','.join(pair_ids)}\t{reason}\n")


def load_corpus(
    *,
    fixtures_dir: Path | None = None,
    payload_dir: Path | None = None,
    include_held_out: bool = False,
    held_out_reason: str = "",
    provenance: str | None = None,
    labelled_only: bool = False,
    allow_stale_guideline: bool = False,
) -> EvalCorpus:
    """Load the corpus. Held-out pairs are excluded unless explicitly unlocked.

    `include_held_out=True` requires `held_out_reason`; the access is logged. This is the
    Stage 0.5 final-validation door and nothing else should be opening it.
    """
    fixtures = fixtures_dir or default_fixtures_dir()
    payloads = payload_dir or default_payload_dir()
    manifest = read_manifest(fixtures)
    # `{sheet_signature: zone_fractions}`, captured by `eval_corpus.py capture-zones`. A
    # signature present here is one the corpus can reproduce offline; a signature absent
    # falls back to the Mongo lookup, which offline means plain detection. See the vault
    # gotcha "Zone Templates Vanish in Offline Eval".
    zone_templates: dict[str, dict[str, Any]] = manifest.get("zone_templates") or {}

    if include_held_out and not held_out_reason.strip():
        raise HeldOutAccessError(
            "include_held_out=True requires held_out_reason. The three held-out pairs are "
            "touched exactly once, at the end of Stage 0.5; every access is logged so that "
            "an accidental use is visible rather than forgotten."
        )

    pairs: list[CorpusPair] = []
    unlocked: list[str] = []
    for entry in manifest.get("pairs") or []:
        is_held_out = bool(entry.get("held_out"))
        if is_held_out:
            if not include_held_out:
                continue
            unlocked.append(str(entry.get("pair_id")))
        if provenance and entry.get("provenance") != provenance:
            continue

        pair_id = str(entry.get("pair_id") or "")
        label_state = str(entry.get("label_state") or "unlabelled")
        labels: PairLabels | None = None
        label_rel = entry.get("labels")
        if label_rel:
            label_path = fixtures / str(label_rel)
            if not label_path.exists():
                raise LabelSchemaError(
                    f"Manifest points pair {pair_id!r} at {label_path}, which does not "
                    f"exist. Hand-authored label files are committed — this is a missing "
                    f"file, not a gitignored payload."
                )
            labels = PairLabels.from_dict(
                json.loads(read_text_stable(label_path)),
                allow_stale_guideline=allow_stale_guideline,
            )
        elif entry.get("mutation"):
            # Generated labels live beside their payload, untracked. They are not human
            # work: the manifest carries the recipe (base pair, side, seed, operators) that
            # reproduces them exactly, so committing them would duplicate the recipe while
            # adding a large surface of customer drawing text to git. Their sha256 is still
            # in the manifest, so drift is caught the same way a payload's is.
            generated = payloads / pair_id / "labels.json"
            if generated.exists():
                expected = str(entry.get("labels_sha256") or "")
                text = read_text_stable(generated)
                actual = sha256_text(text)
                if expected and actual != expected:
                    raise CorpusDriftError(
                        f"{pair_id}: generated labels at {generated} have drifted.\n"
                        f"  manifest: {expected}\n  on disk:  {actual}\n"
                        f"Regenerate with `tools/eval_corpus.py mutate --regenerate`, which "
                        f"reproduces them from the recorded seed — do not hand-edit a "
                        f"generated label file."
                    )
                labels = PairLabels.from_dict(
                    json.loads(text), allow_stale_guideline=allow_stale_guideline
                )

        if labelled_only and label_state != "labelled":
            continue

        pairs.append(
            CorpusPair(
                pair_id=pair_id,
                provenance=str(entry.get("provenance") or "human"),
                held_out=is_held_out,
                label_state=label_state,
                ref=PairSide.from_dict(entry.get("ref") or {}, zone_templates),
                rev=PairSide.from_dict(entry.get("rev") or {}, zone_templates),
                labels=labels,
                notes=str(entry.get("notes") or ""),
                payload_dir=payloads,
                mutation=entry.get("mutation") or None,
                labels_sha256=str(entry.get("labels_sha256") or ""),
            )
        )

    if unlocked:
        _record_held_out_access(held_out_reason, unlocked)

    return EvalCorpus(
        pairs=pairs,
        fixtures_dir=fixtures,
        payload_dir=payloads,
        held_out_included=include_held_out,
    )
