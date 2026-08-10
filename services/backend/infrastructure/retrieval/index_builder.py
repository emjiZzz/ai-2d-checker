"""Builds the retrieval indexes from their sources.

Two collections at R1:

| Collection     | Source today                                   | Source after R3          |
| :------------- | :--------------------------------------------- | :----------------------- |
| `standards`    | `StandardChunk` documents in MongoDB            | unchanged                |
| `domain_rules` | client rule notes in the vault, split by heading | the compiled rule bundle |

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
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ...logger import logger
from ..storage.path_resolver import get_storage_root
from .encoder import EncoderError
from .lexical import TfidfEncoder
from .store import Manifest, Record, VectorStore

STANDARDS = "standards"
DOMAIN_RULES = "domain_rules"
LESSONS = "lessons"

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
        records.append(
            Record(
                id=_record_id(source, heading or str(i)),
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

    records: list[Record] = []
    for path in sorted(rules_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as err:
            logger.warning(f"[retrieval] Could not read {path.name}: {err}")
            continue
        records.extend(chunk_markdown_by_heading(text, source=path.stem))
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
    return BuildResult(collection, len(records), built=True)


def _digest(texts: Sequence[str]) -> str:
    """Content digest of the indexed corpus, so a rebuild can be told from a no-op."""
    sha = hashlib.sha256()
    for text in texts:
        sha.update(text.encode("utf-8"))
        sha.update(b"\x00")
    return f"sha256:{sha.hexdigest()}"


def current_manifest(collection: str, root: Path | None = None) -> Manifest | None:
    return store_for(collection, root).manifest()
