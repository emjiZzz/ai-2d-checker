"""The durable query store — Stage B of the corpus widening ([[ADR-012]]).

A query and a relevance judgement have different lifetimes, and conflating them is what makes a
retrieval corpus expensive to grow. `labels.LabelSet` pins the `source_digest` of the index it
was authored against and `assert_matches_index` refuses to score across a mismatch — so every time
the corpus grows, every label written so far dies. That is correct: a judgement about *which chunk
answers this* is only meaningful against the chunks that existed when it was made.

A query has no such dependency. "What did a checker actually ask?" is a fact about the checker,
not about the index, and it survives any number of rebuilds. Queries are also the input that takes
longest to gather and that no tooling can synthesise — see the guideline's *"Where queries come
from"*, which is emphatic that a query written while looking at a chunk is a paraphrase of that
chunk and measures nothing.

So this store deliberately records neither `source_digest` nor `guideline_version`:

* no `source_digest`, because a query does not become wrong when the corpus changes — that is the
  entire reason Stage B can run before Stage C, and in parallel with more sources landing;
* no `guideline_version`, because the guideline governs what counts as *relevant*. Re-judging
  relevance under a new rule does not un-ask the question.

Both are pinned on the *label* instead, which is where the corpus dependency actually lives.
Guarded by `tests/test_retrieval_query_store.py`.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..storage.path_resolver import get_storage_root

QUERY_SCHEMA_VERSION = 1

#: Cap copied from `audit_orchestrator._retrieve_lessons_learned`, where it bounds the MongoDB
#: fallback's keyword list. Kept here because this module now owns the construction.
MAX_QUERY_KEYWORDS = 20


class QueryOrigin(StrEnum):
    """Where a query came from. Required, for the same reason `labels.Provenance` is.

    A query the *system* generates and a question a *person* asked are different evidence about
    what retrieval is for, and the difference disappears the moment they share a file.
    """

    #: Reproduced from the pipeline's own query construction. Real in the sense that matters —
    #: it is literally what production searches with — but every one has the same shape, so a
    #: set made only of these measures the production path, not a checker's need.
    PRODUCTION = "production"
    #: A person asked this during a review. The guideline's best source, and the only one that
    #: cannot be generated.
    CHECKER = "checker"
    #: A finding that was raised, rephrased as the question it should have been checked against.
    FINDING = "finding"


class QueryStoreError(RuntimeError):
    """A query set is malformed, or an entry is missing a required field."""


@dataclass(frozen=True)
class RetrievalQuery:
    query_id: str
    query: str
    origin: QueryOrigin
    note: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["origin"] = str(self.origin)
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RetrievalQuery:
        missing = {"query_id", "query", "origin"} - set(raw)
        if missing:
            raise QueryStoreError(f"Query is missing required field(s): {sorted(missing)}")
        if not str(raw["query"]).strip():
            raise QueryStoreError(f"Query {raw['query_id']!r} has no text.")
        try:
            origin = QueryOrigin(raw["origin"])
        except ValueError as err:
            raise QueryStoreError(
                f"Query {raw['query_id']!r} has origin {raw['origin']!r}; expected one of "
                f"{[str(o) for o in QueryOrigin]}. Origin is required because a query the system "
                f"generated and a question a person asked are not the same evidence."
            ) from err
        return cls(
            query_id=str(raw["query_id"]),
            query=str(raw["query"]),
            origin=origin,
            note=raw.get("note", ""),
            created_at=raw.get("created_at", ""),
        )


@dataclass
class QuerySet:
    collection: str
    queries: list[RetrievalQuery] = field(default_factory=list)
    schema_version: int = QUERY_SCHEMA_VERSION

    def counts_by_origin(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for q in self.queries:
            counts[str(q.origin)] = counts.get(str(q.origin), 0) + 1
        return counts

    def add(
        self,
        query: str,
        origin: QueryOrigin,
        note: str = "",
    ) -> RetrievalQuery | None:
        """Append a query, or return `None` if its text is already present.

        Deduplicated on the query *text*, because two identical questions are one question and
        scoring the same query twice would weight it double against a 30-query gate.
        """
        text = query.strip()
        if not text:
            raise QueryStoreError("Refusing to store an empty query.")
        if any(q.query == text for q in self.queries):
            return None

        # Scanned rather than derived from the length. `drop_origin` leaves gaps — a store
        # holding q001(checker) after q002(production) went would otherwise mint a second q001
        # on the next add, silently giving two different questions the same address.
        existing = {q.query_id for q in self.queries}
        n = len(self.queries) + 1
        while f"q{n:03d}" in existing:
            n += 1

        entry = RetrievalQuery(
            query_id=f"q{n:03d}",
            query=text,
            origin=origin,
            note=note,
            created_at=datetime.now(UTC).isoformat(),
        )
        self.queries.append(entry)
        return entry

    def drop_origin(self, origin: QueryOrigin) -> int:
        """Remove every query of one origin, returning how many went. Ids are not renumbered.

        Exists for `production`, which is a *projection* of the current query construction over
        the current drawings — so a harvest must be idempotent, and re-running it after the
        construction changes must not leave the store holding queries production can no longer
        issue alongside the new ones.

        Never call this with a human origin. `checker` and `finding` queries are the input
        nothing can regenerate; that asymmetry is the entire reason `QueryOrigin` is required.
        Guarded by `test_dropping_a_human_origin_is_refused`.
        """
        if origin is not QueryOrigin.PRODUCTION:
            raise QueryStoreError(
                f"Refusing to drop {origin!r} queries. Only 'production' is derived and therefore "
                f"regenerable; a question a person asked cannot be recovered by re-running a tool."
            )
        before = len(self.queries)
        self.queries = [q for q in self.queries if q.origin is not origin]
        return before - len(self.queries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection": self.collection,
            "schema_version": self.schema_version,
            "queries": [q.to_dict() for q in self.queries],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QuerySet:
        if "collection" not in raw:
            raise QueryStoreError("Query set is missing 'collection'.")
        version = int(raw.get("schema_version", QUERY_SCHEMA_VERSION))
        if version != QUERY_SCHEMA_VERSION:
            raise QueryStoreError(
                f"Query set is schema v{version}; this build reads v{QUERY_SCHEMA_VERSION}."
            )
        return cls(
            collection=str(raw["collection"]),
            queries=[RetrievalQuery.from_dict(q) for q in raw.get("queries", [])],
            schema_version=version,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, collection: str) -> QuerySet:
        """Load, or return an empty set if the file does not exist yet.

        An absent file is normal operation — nobody has recorded a query for this collection —
        and is not the same as a malformed one, which raises.
        """
        if not path.exists():
            return cls(collection=collection)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise QueryStoreError(f"{path.name} is not valid JSON: {err}") from err
        return cls.from_dict(raw)


def queries_root() -> Path:
    """Under the gitignored storage tree, deliberately.

    A harvested production query embeds the drawing's file name — customer data — so this store
    is local-only, like the eval corpus payloads and for the same reason. Committing it would put
    client drawing numbers in the repository.
    """
    return get_storage_root() / "retrieval" / "queries"


def default_queries_path(collection: str) -> Path:
    return queries_root() / f"queries-{collection}.json"


# ---------------------------------------------------------------------------
# The production query
# ---------------------------------------------------------------------------

_SPLIT_LAYER = re.compile(r"[_\-\s]+")
_SPLIT_FILENAME = re.compile(r"[_\-\s\.]+")

#: Layer-name and file-stem fragments shorter than these carry no signal. Both thresholds are
#: the ones `_retrieve_lessons_learned` has always used and are reproduced exactly — this
#: function must build the query production *actually* searches with, or a measurement taken
#: against it describes something the product does not do.
_MIN_LAYER_PART = 2
_MIN_STEM_PART = 3


def build_drawing_keywords(drawing: Any, layer_names: Iterable[str] = ()) -> list[str]:
    """The deduplicated, capped keyword list the audit pipeline derives from a drawing.

    Separate from `build_drawing_query` because the orchestrator needs both: the joined
    query text for the lexical index, and the keyword list for the MongoDB substring fallback.
    Deriving the second by splitting the first on spaces would corrupt it for any drawing whose
    file name contains a space.

    `layer_names` is a parameter, not something read off the drawing, and that is the fix
    for a defect rather than a style choice. Until 2026-08-17 this read
    `drawing.metadata["layers"]` — a key nothing has ever written — so the branch its own
    comment called *"the strongest signal"* contributed nothing on all 44 drawings in the
    database, and a production query was the file name plus a constant. Layer names live on
    `ExtractedEntity.layer`, one collection over, indexed. Passing them in keeps this function
    synchronous and testable while making the source explicit at each call site.
    See [[Gotcha - The Strongest Signal in the Audit Query Was Never Written]].

    Duck-typed on `file_name` and `entity_counts` so it stays testable without a database.
    """
    keywords: list[str] = []

    # 1. Layer names are the strongest signal (e.g. "BORDER", "DIMENSION", "GEOMETRY").
    for layer in layer_names:
        if isinstance(layer, str) and layer.strip():
            parts = _SPLIT_LAYER.split(layer.upper())
            keywords.extend(p.lower() for p in parts if len(p) > _MIN_LAYER_PART)

    # 2. Entity types from entity_counts (e.g. "line", "dimension", "text", "hatch").
    for entity_type in (getattr(drawing, "entity_counts", None) or {}):
        keywords.append(entity_type.lower())

    # 3. File name stem can hint at part type (e.g. "anchor_bolt", "flange_detail").
    file_name = getattr(drawing, "file_name", "") or ""
    stem_parts = _SPLIT_FILENAME.split(file_name)
    keywords.extend(p.lower() for p in stem_parts if len(p) > _MIN_STEM_PART)

    return list(dict.fromkeys(keywords))[:MAX_QUERY_KEYWORDS]


def drawing_query_text(file_name: str, keywords: list[str]) -> str:
    """Join a file name and its keywords into the query string. One place, two callers."""
    return f"{file_name} " + " ".join(keywords)


def build_drawing_query(drawing: Any, layer_names: Iterable[str] = ()) -> str | None:
    """The query the audit pipeline searches `standards` with, for one drawing.

    Extracted from `AuditOrchestrator._retrieve_lessons_learned` on 2026-08-17 so that Stage B
    can harvest real production queries without reimplementing how one is built. A harvester
    that built a nearly-identical query would measure something the product does not do — the
    same defect one layer up from `mutator.py` sharing `apply_zone_overrides` with the engine.

    Returns `None` when no keyword survives, matching the orchestrator's skip.
    """
    keywords = build_drawing_keywords(drawing, layer_names)
    if not keywords:
        return None
    return drawing_query_text(getattr(drawing, "file_name", "") or "", keywords)


async def layer_names_for(drawing_id: str) -> list[str]:
    """Distinct layer names on one drawing, sorted.

    Sorted because the keyword order it produces ends up in the query text, and an unordered
    `set` would make the same drawing yield a different query on every run — which would defeat
    the query store's text-level deduplication and make a harvest non-idempotent.

    Uses the `(drawing_id, layer)` compound index rather than loading entities: this runs inside
    an audit, and the drawings here carry thousands of entities each.
    """
    from ...domain.models.extracted_entity import ExtractedEntity  # noqa: PLC0415

    collection = ExtractedEntity.get_pymongo_collection()
    names = await collection.distinct("layer", {"drawing_id": drawing_id})
    return sorted(n for n in names if isinstance(n, str) and n.strip())
