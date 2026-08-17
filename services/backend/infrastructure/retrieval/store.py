"""On-disk index: a sparse matrix, a JSONL sidecar of records, and a manifest.

Search is an exact brute-force cosine over every record — no approximation, no index structure.

**Why an empty index is a first-class state.** The staged plan names this as R1's risk: *"an empty
index returns zero results, which is indistinguishable from 'nothing relevant'."* That is the same
shape as the R0 defect, where a read path returning `[]` concealed a write path that never wrote.
So `search()` does not return a bare list. It returns a `SearchOutcome` carrying a `status`, and
`MISSING` / `EMPTY` / `STALE` are distinct from `OK` with no hits. Callers that ignore the status
still behave correctly; callers that check it can tell the difference.
"""

# Design rationale, deliberately in comments rather than the docstring above. Naming a library
# in order to say "we rejected it" is not a capability claim, but a docstring is where a module
# states what it *is* — and `tests/test_no_fake_ai_capability.py` reads docstrings as claims for
# exactly that reason. History and rejected alternatives live here.
#
# BRUTE FORCE ON PURPOSE. Adding an approximate-nearest-neighbour library (the usual suspects:
# LanceDB, FAISS, Chroma, Qdrant) is a recorded negative result in the maturity ledger: at
# <=100k short strings an exact sparse dot product is ~1 ms, so an ANN index buys nothing and
# costs a dependency, a build step, and an approximation. The module R0 deleted had the right
# algorithm and the wrong name; the algorithm is what survives here.
#
# SPARSE .npz, WHERE THE PLAN SAID .npy. Deliberate deviation, recorded rather than quiet. Char
# n-gram TF-IDF is inherently sparse, so a dense array of it is the wrong container: at 2**16
# features a dense float32 row costs 256 KB *per chunk* and is ~99.9% zeros, while the CSR form
# of the same data is a few KB. Identical results, correct container.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, load_npz, save_npz

from ...logger import logger

#: Bump when the on-disk layout changes shape, **or when what a record means changes**. An index
#: written under an older version is refused rather than misread — the manifest is checked on
#: every load, and `bootstrap_retrieval_indexes` rebuilds anything that does not report OK.
#:
#: v2: `build_index` collapses byte-identical texts. A v1 index can hold the same text more than
#: once, so its `n_records` overstates the number of distinguishable answers — which is the
#: denominator of the chance floor every retrieval verdict is gated on. A stale v1 index is not
#: merely old, it reports a corpus size that is not true.
INDEX_SCHEMA_VERSION = 2

_MATRIX_FILE = "vectors.npz"
_RECORDS_FILE = "records.jsonl"
_MANIFEST_FILE = "manifest.json"


class IndexStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"          # never built
    EMPTY = "empty"              # built, but holds zero records
    STALE = "stale"              # built by a different encoder or schema version


@dataclass(frozen=True)
class Record:
    """One retrievable unit, and everything needed to cite it back to a human.

    Citation is not decoration here. [[ADR-008]] chose retrieval-only — *"here are the three
    clauses that apply"* rather than a generated paragraph — and that product only works if every
    hit can name where it came from. A hit with no `source` is not useful to a checker.
    """

    id: str
    text: str
    source: str                       # human-readable origin, e.g. the standard's name
    section: str | None = None        # heading within the source
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation(self) -> str:
        """Human-readable provenance, e.g. `JIS B 0405 > TOLERANCES > p.12`.

        **ASCII separator on purpose.** This string is logged, and the console on a Japanese
        Windows install is cp932, which cannot encode `·` (U+00B7) — a citation containing one
        raises `UnicodeEncodeError` at the log call rather than at any point near the bug. The
        record text itself is of course Japanese; it is only the punctuation *we* add that has to
        survive the narrowest encoding in the stack. Same class as
        [[Gotcha - AutoCAD Control Escape Codes]].
        """
        parts = [self.source]
        if self.section:
            parts.append(self.section)
        if self.page is not None:
            parts.append(f"p.{self.page}")
        return " > ".join(parts)


@dataclass(frozen=True)
class Hit:
    record: Record
    score: float
    rank: int


@dataclass(frozen=True)
class SearchOutcome:
    """Hits plus *why* there are that many. See the module docstring."""

    hits: list[Hit]
    status: IndexStatus
    collection: str
    detail: str = ""

    def __bool__(self) -> bool:
        return bool(self.hits)

    @property
    def answered(self) -> bool:
        """True when the index was in a position to answer, hits or not."""
        return self.status is IndexStatus.OK


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    encoder_name: str
    collection: str
    n_records: int
    built_at: str
    source_digest: str = ""

    @staticmethod
    def load(path: Path) -> Manifest:
        return Manifest(**json.loads(path.read_text(encoding="utf-8")))

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


class VectorStore:
    """One collection's index on disk, and exact cosine search over it."""

    def __init__(self, directory: Path, collection: str) -> None:
        self.directory = directory
        self.collection = collection
        self._matrix: csr_matrix | None = None
        self._records: list[Record] = []
        self._manifest: Manifest | None = None

    # -- paths ------------------------------------------------------------------

    @property
    def matrix_path(self) -> Path:
        return self.directory / _MATRIX_FILE

    @property
    def records_path(self) -> Path:
        return self.directory / _RECORDS_FILE

    @property
    def manifest_path(self) -> Path:
        return self.directory / _MANIFEST_FILE

    def exists(self) -> bool:
        return self.manifest_path.exists() and self.records_path.exists()

    # -- write ------------------------------------------------------------------

    def write(
        self,
        matrix: csr_matrix,
        records: list[Record],
        encoder_name: str,
        source_digest: str = "",
    ) -> Manifest:
        if matrix.shape[0] != len(records):
            raise ValueError(
                f"{matrix.shape[0]} vectors for {len(records)} records in collection "
                f"'{self.collection}'. These are positionally paired — a mismatch would return "
                f"the wrong chunk for a hit, which is worse than returning none."
            )

        self.directory.mkdir(parents=True, exist_ok=True)
        save_npz(self.matrix_path, matrix)
        with self.records_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

        manifest = Manifest(
            schema_version=INDEX_SCHEMA_VERSION,
            encoder_name=encoder_name,
            collection=self.collection,
            n_records=len(records),
            built_at=datetime.now(UTC).isoformat(),
            source_digest=source_digest,
        )
        manifest.dump(self.manifest_path)

        self._matrix, self._records, self._manifest = matrix, records, manifest
        logger.info(
            f"[retrieval] Indexed {len(records)} record(s) into '{self.collection}' "
            f"({encoder_name}) at {self.directory}"
        )
        return manifest

    # -- read -------------------------------------------------------------------

    def load(self, expected_encoder: str | None = None) -> IndexStatus:
        if not self.exists():
            return IndexStatus.MISSING

        manifest = Manifest.load(self.manifest_path)
        if manifest.schema_version != INDEX_SCHEMA_VERSION:
            return IndexStatus.STALE
        if expected_encoder is not None and manifest.encoder_name != expected_encoder:
            return IndexStatus.STALE
        if manifest.n_records == 0:
            self._manifest, self._records, self._matrix = manifest, [], None
            return IndexStatus.EMPTY

        self._records = [
            Record(**json.loads(line))
            for line in self.records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self._matrix = load_npz(self.matrix_path).tocsr()
        self._manifest = manifest

        if self._matrix.shape[0] != len(self._records):
            return IndexStatus.STALE
        return IndexStatus.OK

    def search(
        self,
        query_vector: csr_matrix,
        top_k: int = 5,
        min_score: float = 0.0,
        expected_encoder: str | None = None,
    ) -> SearchOutcome:
        """Exact cosine over every record. Vectors are L2-normalised, so this is a dot product."""
        status = self.load(expected_encoder=expected_encoder)

        if status is not IndexStatus.OK:
            detail = {
                IndexStatus.MISSING: (
                    f"No index for collection '{self.collection}' at {self.directory}. Nothing "
                    f"has been indexed yet — this is not the same as having no relevant results."
                ),
                IndexStatus.EMPTY: (
                    f"Index for '{self.collection}' exists but holds zero records. Every query "
                    f"against it will return nothing regardless of what is asked."
                ),
                IndexStatus.STALE: (
                    f"Index for '{self.collection}' was built by a different encoder or schema "
                    f"version and cannot be searched. Rebuild it."
                ),
            }[status]
            logger.warning(f"[retrieval] {detail}")
            return SearchOutcome(hits=[], status=status, collection=self.collection, detail=detail)

        assert self._matrix is not None  # guaranteed by IndexStatus.OK

        # (n_records, dim) @ (dim, 1) -> (n_records, 1). Exact; no approximation anywhere.
        similarities = np.asarray((self._matrix @ query_vector.T).todense()).ravel()

        k = min(top_k, similarities.shape[0])
        # argpartition is O(n) to find the top k, then only those k are sorted.
        top_idx = np.argpartition(-similarities, k - 1)[:k] if k > 0 else np.array([], dtype=int)
        top_idx = top_idx[np.argsort(-similarities[top_idx])]

        hits = [
            Hit(record=self._records[int(i)], score=float(similarities[i]), rank=rank)
            for rank, i in enumerate(top_idx, start=1)
            if similarities[i] > min_score
        ]
        return SearchOutcome(hits=hits, status=IndexStatus.OK, collection=self.collection)

    # -- introspection ----------------------------------------------------------

    @property
    def records(self) -> list[Record]:
        return list(self._records)

    def manifest(self) -> Manifest | None:
        if self._manifest is None and self.manifest_path.exists():
            self._manifest = Manifest.load(self.manifest_path)
        return self._manifest
