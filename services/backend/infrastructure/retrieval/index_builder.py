"""Builds the retrieval indexes from their sources.

| Collection     | Source                                  | Trust level              |
| :------------- | :-------------------------------------- | :----------------------- |
| `standards`    | `StandardChunk` documents in MongoDB    | published standard       |
| `domain_rules` | client rule notes in the vault          | client-authored rule     |
| `lessons`      | **APPROVED** `AuditViolation`s          | a human confirmed it     |
| `corrections`  | non-retracted `AuditFeedbackDocument`s  | a human corrected it     |
| `findings`     | **every** `AuditViolation`              | mostly unreviewed output |
| `vault`        | `docs/vault/**/*.md`, by heading        | engineering knowledge    |
| `entities`     | `ExtractedEntity` text                  | raw drawing content      |

⚠ **`vault` is knowledge about the *system*, not about a drawing.** It answers *"why is this built
this way"*, which serves an agent or the copilot; it does not answer *"what does this tolerance
mean"*. Do not read a healthy record count here as coverage of the checker's domain.

⚠ **`entities` is customer drawing content**, so it is client-local and carries the same privacy
edge as `checker_remarks` — see `service.violation_record`. Local-only at R1.

⚠ **`lessons` is a subset of `findings`, deliberately, and they are separate collections because
the chance floor is per-collection.** `metrics.chance_recall_at_k` is `k/N` over one collection's
own `n_records`, so a 17-record `lessons` cannot be measured no matter how much is indexed
elsewhere. They share `service.violation_record` so the two can never disagree about how a
violation becomes text.

⚠ **A `findings` hit is not knowledge.** Most of that collection has never been reviewed, so its
records carry their review state in `Record.source` ("Confirmed finding" / "Rejected finding" /
"Unreviewed finding") rather than only in metadata — a citation that does not say whether a human
ever agreed is the "near-miss rules surfaced as authoritative" hazard [[ADR-008]] named.

**Why `domain_rules` reads markdown at R1 when the plan says "from the bundle".** The bundle is an
R3 deliverable and does not exist yet. Rather than block, the source is expressed as a *function
returning records* (`RecordSource`) instead of a path, so R3 swaps the source and touches nothing
else. That is the same "bundle source abstraction rather than a path" seam R3 was already going to
build — building it here costs nothing and means R1 ships working retrieval over the rules that
exist today.

**The fetch/fit split is load-bearing, not stylistic.** Fetching is async (Mongo); fitting a
TF-IDF vocabulary over the corpus is CPU-bound. They are separate functions so the CPU half is a
plain synchronous callable that `asyncio.to_thread` can offload — see
`StandardsLoader.ingest_standard`, and the guard in `tests/test_standards_loader_async.py`. The
predecessor called indexing inline from an async function; that was survivable only because the
"embedding" it computed was a random number generator. Real TF-IDF fitting is not.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ...logger import logger
from ..storage.path_resolver import get_storage_root
from ..utils.text import strip_mtext
from .encoder import EncoderError
from .lexical import TfidfEncoder
from .store import Manifest, Record, VectorStore

STANDARDS = "standards"
DOMAIN_RULES = "domain_rules"
LESSONS = "lessons"
#: Stage A (2026-08-17): the human-judgement collections. Both are sourced from the local
#: MongoDB, so both are **client-local** — see `tools/retrieval_eval.py::CLIENT_LOCAL_COLLECTIONS`.
CORRECTIONS = "corrections"
FINDINGS = "findings"
#: Stage A, second pass. `ENTITIES` is customer drawing content and therefore client-local;
#: `VAULT` is git-tracked and identical on every install at a given commit, so it is **not**.
VAULT = "vault"
ENTITIES = "entities"

#: A source is anything that can produce records. Not a path — see the module docstring.
RecordSource = Callable[[], Sequence[Record]]


def index_root() -> Path:
    """Where indexes live. Sibling of the other local artifacts, under the storage sandbox."""
    return get_storage_root() / "retrieval"


def store_for(collection: str, root: Path | None = None) -> VectorStore:
    return VectorStore((root or index_root()) / collection, collection)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.M)
_FENCE = re.compile(r"```.*?```", re.S)

#: Below this, a "chunk" is a heading with no body — noise in a ranking, and it dilutes idf.
MIN_CHUNK_CHARS = 24


def chunk_markdown_by_heading(text: str, source: str) -> list[Record]:
    """Split a markdown note into one record per heading section.

    Fenced code blocks are stripped first. This mirrors `vault_sync._strip_fenced_blocks`, and for
    the same reason it was added there: a mermaid diagram or a frontmatter block inside a fence is
    not prose a checker would ever want cited back at them, and including it lets diagram syntax
    win keyword matches. That bug has been paid for once in this codebase already.
    """
    body = _FENCE.sub(" ", text)
    matches = list(_HEADING.finditer(body))
    records: list[Record] = []
    # A record id is `sha256(f"{source}::{discriminator}")`, and a heading is **not unique within
    # a note**: `AI Maturity Ladder — Staged Plan` carries six `Exit criterion` sections, one per
    # stage. Without this counter all six hash to one id, so twelve of the vault's 990 chunks
    # shared four ids. Harmless while nothing pins a chunk id, and fatal at the moment a relevance
    # label names one — which is exactly what `RetrievalLabel.relevant_ids` does.
    #
    # Only *repeats* are suffixed, so a note with unique headings keeps byte-identical ids and no
    # existing collection's ids move. See
    # [[Gotcha - One Heading Twice in a Note Is One Retrieval Record]].
    seen_headings: Counter[str] = Counter()

    if not matches:
        stripped = body.strip()
        if len(stripped) >= MIN_CHUNK_CHARS:
            records.append(
                Record(id=_record_id(source, "0"), text=stripped, source=source, section=None)
            )
        return records

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        if not section_body:
            continue

        # The heading is prepended to the indexed text on purpose: it is usually the most
        # topical line in the section, and a char n-gram model has no other way to know that
        # "TOLERANCES" is what the paragraph beneath it is about.
        combined = f"{heading}\n{section_body}"
        if len(combined) < MIN_CHUNK_CHARS:
            continue

        # Counted only for headings that actually become a record, so the numbering is dense
        # over what is indexed rather than over what was parsed.
        key = heading or str(i)
        seen_headings[key] += 1
        occurrence = seen_headings[key]
        discriminator = key if occurrence == 1 else f"{key}#{occurrence}"

        records.append(
            Record(
                id=_record_id(source, discriminator),
                text=combined,
                source=source,
                section=heading,
            )
        )
    return records


def _record_id(source: str, discriminator: str) -> str:
    digest = hashlib.sha256(f"{source}::{discriminator}".encode()).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def records_from_standard_chunks(chunks: Iterable) -> list[Record]:
    """Adapt `StandardChunk` documents into retrieval records.

    Takes already-fetched documents rather than querying, so this stays synchronous and testable
    without a database.
    """
    records: list[Record] = []
    for chunk in chunks:
        content = (getattr(chunk, "content", "") or "").strip()
        if not content:
            continue
        header = getattr(chunk, "section_header", None)
        metadata = getattr(chunk, "metadata", None) or {}
        records.append(
            Record(
                id=str(getattr(chunk, "id", "") or _record_id("standard", content[:64])),
                text=f"{header}\n{content}" if header else content,
                source=metadata.get("standard_name") or getattr(chunk, "standard_id", "standard"),
                section=header,
                page=metadata.get("page_number"),
                metadata={
                    "standard_id": getattr(chunk, "standard_id", ""),
                    "chunk_index": getattr(chunk, "chunk_index", None),
                },
            )
        )
    return records


def _records_from_markdown_tree(
    root: Path,
    exclude_dirs: frozenset[str] = frozenset(),
) -> list[Record]:
    """Every markdown note under `root`, chunked by heading, skipping `exclude_dirs`.

    Shared by `records_from_rule_notes` and `records_from_vault_notes` because "walk the tree,
    chunk by heading, name the record after the file" is one rule. Two copies of it would keep
    working while drifting on encoding, sort order or what counts as a note.
    """
    records: list[Record] = []
    for path in sorted(root.rglob("*.md")):
        if exclude_dirs and any(
            part in exclude_dirs for part in path.relative_to(root).parts[:-1]
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as err:
            logger.warning(f"[retrieval] Could not read {path.name}: {err}")
            continue
        records.extend(chunk_markdown_by_heading(text, source=path.stem))
    return records


def records_from_rule_notes(rules_dir: Path) -> list[Record]:
    """Every markdown note under `rules_dir`, chunked by heading.

    The directory is gitignored client domain data, so this must tolerate its absence — on a
    fresh clone or in CI it will not exist, and that is normal operation, not an error.
    """
    if not rules_dir.exists():
        logger.info(
            f"[retrieval] No client rules directory at {rules_dir}; the '{DOMAIN_RULES}' "
            f"collection will not be built. This is normal on a machine without client data."
        )
        return []

    return _records_from_markdown_tree(rules_dir)


def records_from_vault_notes(
    vault_dir: Path,
    exclude_dirs: frozenset[str] = frozenset(),
) -> list[Record]:
    """The Obsidian knowledge base, chunked by heading.

    `exclude_dirs` is supplied by the caller rather than hardcoded here, so the names of the
    excluded directories live in exactly one place — `service.rebuild_vault_index` derives them
    from `VaultSyncManager.CLIENT_RULES_DIR` and `learning.config.MODEL_DIRNAME` rather than
    restating two magic strings that would then be free to drift from their owners.

    **Both exclusions are load-bearing.** The client-rules directory is already the `domain_rules`
    collection, so indexing it here would put identical text in two collections with different
    trust levels; and the learned-models directory is a gitignored generated artifact, so
    including it would make an otherwise reproducible collection vary per install.
    """
    if not vault_dir.exists():
        logger.info(
            f"[retrieval] No vault at {vault_dir}; the '{VAULT}' collection will not be built."
        )
        return []

    return _records_from_markdown_tree(vault_dir, exclude_dirs)


#: Below this, an entity's text is not something any real query retrieves — a stray `A`, a bare
#: `1`, a leader's single-character tag. **A convention, not a measured optimum**, in the same
#: sense `min_structured_value_length` was one: nothing here has been swept, and the corpus to
#: sweep it against is what Stage A is building. Recorded as arbitrary rather than dressed up.
MIN_ENTITY_TEXT_CHARS = 3

#: How many duplicate citations the collapse reports at WARNING before deferring the rest to
#: DEBUG. Enough to trace a small corpus's drops in full; small enough that `lessons` — rebuilt
#: on every supervisor verdict, dropping ~67 each time — costs one log line rather than 67.
MAX_LOGGED_DUPLICATE_CITATIONS = 5


def records_from_entities(
    entities: Iterable,
    drawing_names: dict[str, str] | None = None,
) -> list[Record]:
    """Adapt `ExtractedEntity` documents carrying text into retrieval records.

    Text is read as `properties["text"] or properties["value"]` and normalised through
    `strip_mtext` — the same two rules the comparison engine uses
    (`candidate_generator.py:462`). Reading the raw property here would let this collection
    disagree with the engine about what an entity *says*, which is the drift shape this codebase
    keeps paying for.

    `drawing_names` maps `drawing_id` to a human-readable file name so a citation reads
    `M745230A01.dxf > NOTES` rather than a 32-character hex id. Absent, the id is used.

    ⚠ **This is customer drawing content.** Local-only at R1; strip at the edge before anything
    is transmitted. See `service.violation_record` for the same constraint on `checker_remarks`.
    """
    names = drawing_names or {}
    records: list[Record] = []

    for entity in entities:
        properties = getattr(entity, "properties", None) or {}
        raw = properties.get("text") or properties.get("value") or ""
        text = strip_mtext(raw).strip()
        if len(text) < MIN_ENTITY_TEXT_CHARS:
            continue

        drawing_id = getattr(entity, "drawing_id", "") or ""
        layer = getattr(entity, "layer", "") or "0"
        records.append(
            Record(
                id=str(getattr(entity, "id", "") or _record_id("entity", f"{drawing_id}:{text}")),
                text=text,
                source=names.get(drawing_id, drawing_id or "drawing"),
                section=layer,
                metadata={
                    "drawing_id": drawing_id,
                    "layer": layer,
                    "entity_type": getattr(entity, "entity_type", ""),
                    "handle": getattr(entity, "handle", None),
                },
            )
        )
    return records


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BuildResult:
    collection: str
    n_records: int
    built: bool
    reason: str = ""
    #: How many records were dropped as byte-identical copies of an earlier one. Reported rather
    #: than swallowed: a non-zero count here is a fact about the *source*, and the source is where
    #: it should be fixed. See `_collapse_duplicate_texts`.
    n_duplicates_dropped: int = 0


def _collapse_duplicate_texts(
    collection: str,
    records: Sequence[Record],
) -> tuple[list[Record], int]:
    """Keep one record per distinct text, first occurrence wins.

    **This guards the metric's denominator, and it is a net rather than a fix.** `corpus_size` in
    `metrics.py` is `manifest.n_records`, and the chance floor every verdict is gated on is `k/N`
    over that count. Index the same text twice and N doubles while the number of *distinguishable*
    answers does not, so the floor halves and a corpus reports itself as discriminating when it is
    not. Duplicates also score identically, so they take adjacent slots and a top-5 returns three
    answers wearing five badges; and each relevant chunk acquires a twin, which pushes an
    annotator's mean `relevant_ids` toward 2 and raises the `n_relevant` term of
    `chance_recall_at_k` — so the floor climbs on the inflated count too. Both routes end at "not
    informative", by different arithmetic.

    ⚠ **This would not have caught the incident that prompted it, and saying so is the point.** On
    2026-08-14 `standards` reported 32 records that were 16 texts each present twice. The source
    was not a double ingest — `build_index` never saw 32 records. Mongo held one standard and 16
    chunks; the other 16 were the chunks of a *deleted* standard, still in a stale index that
    `bootstrap_retrieval_indexes` declined to rebuild because it gated on file presence rather
    than on `IndexStatus`. The fix for that is in `service.py`. What this function is for is the
    case that genuinely reaches here: `lessons` in particular, where two approved violations on
    different drawings routinely carry identical text and are one answer to a query.

    **First occurrence wins** so the result is deterministic and the earliest record keeps the
    citation. Each drop is logged with both citations, on the `zone_ownership` principle — anything
    this net catches is a bug upstream, and it stays findable only if the net says what it caught.
    """
    seen: dict[str, Record] = {}
    kept: list[Record] = []
    examples: list[str] = []
    dropped = 0

    for record in records:
        key = hashlib.sha256(record.text.encode("utf-8")).hexdigest()
        first = seen.get(key)
        if first is None:
            seen[key] = record
            kept.append(record)
            continue
        dropped += 1
        citation = f"{record.citation()} duplicates {first.citation()}"
        if len(examples) < MAX_LOGGED_DUPLICATE_CITATIONS:
            examples.append(citation)
        # Full detail stays available, one level down. See the note on the aggregate below.
        logger.debug(f"[retrieval] '{collection}': dropping {citation}. Only the first is indexed.")

    if dropped:
        # **One line, with a bounded sample of citations.** This was a WARNING *per drop* until
        # 2026-08-17, which is fine for a startup build and pathological for `lessons`: that
        # collection is rebuilt on **every supervisor verdict** and drops ~67 duplicates each
        # time, so a single click emitted 67 warnings and buried the one line that matters.
        #
        # The citations are kept rather than moved wholesale to DEBUG, because
        # `test_the_drop_is_reported_rather_than_swallowed` pins a real property: what this net
        # catches is a bug upstream, and it stays findable only if the net says *what* it caught.
        # A bounded sample satisfies that at a bounded cost; the remainder is at DEBUG.
        sample = "; ".join(examples)
        more = dropped - len(examples)
        overflow = f" (+{more} more at DEBUG)" if more > 0 else ""
        logger.warning(
            f"[retrieval] '{collection}': {len(records)} record(s) collapsed to {len(kept)} "
            f"distinct text(s); {dropped} duplicate(s) dropped. Two records with the same text "
            f"are one answer, and counting them as two inflates the corpus the recall gate is "
            f"measured against - fix this at the source, not here. Dropped: {sample}{overflow}."
        )
    return kept, dropped


def build_index(
    collection: str,
    records: Sequence[Record],
    root: Path | None = None,
) -> BuildResult:
    """Fit an encoder over `records` and write the index. **Synchronous and CPU-bound.**

    Call this via `asyncio.to_thread` from any async context.
    """
    if not records:
        # Deliberately does not write an empty index. An empty index and a missing one are
        # different states (see store.IndexStatus) and the missing one is the honest label for
        # "there was nothing to index" — writing an empty one would assert that a build happened
        # and found nothing, which is a stronger claim.
        logger.info(f"[retrieval] Nothing to index for '{collection}'; skipping build.")
        return BuildResult(collection, 0, built=False, reason="no records")

    records, n_dropped = _collapse_duplicate_texts(collection, records)
    texts = [r.text for r in records]
    encoder = TfidfEncoder()
    try:
        encoder.fit(texts)
        matrix = encoder.encode(texts)
    except EncoderError as err:
        logger.error(f"[retrieval] Encoder refused to build '{collection}': {err}")
        return BuildResult(collection, 0, built=False, reason=str(err))

    store = store_for(collection, root)
    store.write(
        matrix=matrix,
        records=list(records),
        encoder_name=encoder.name,
        source_digest=_digest(texts),
    )
    encoder.save(store.directory)
    return BuildResult(collection, len(records), built=True, n_duplicates_dropped=n_dropped)


def _digest(texts: Sequence[str]) -> str:
    """Content digest of the indexed corpus, so a rebuild can be told from a no-op."""
    sha = hashlib.sha256()
    for text in texts:
        sha.update(text.encode("utf-8"))
        sha.update(b"\x00")
    return f"sha256:{sha.hexdigest()}"


def current_manifest(collection: str, root: Path | None = None) -> Manifest | None:
    return store_for(collection, root).manifest()
