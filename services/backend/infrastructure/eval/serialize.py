"""On-disk payload format for evaluation pairs, and the duck-typed objects it loads into.

`generate_deterministic_candidates` reads exactly five attributes off an entity —
`entity_type`, `layer`, `handle`, `properties`, `geometry` — and four off a drawing —
`id`, `file_name`, `file_hash`, `metadata`. It never calls a Beanie method on either.
That is what makes an offline harness possible at all, so this module deliberately
provides the smallest objects satisfying that surface rather than reusing the Document
subclasses, which would drag in Mongo.

`ExtractedEntity`'s other indexed columns (`parent_handle`, `space`, `viewport_index`) are
carried anyway: they are cheap, they are part of the extraction schema, and omitting them
would make a payload a lossy record of what was extracted.

## Byte stability is a feature, not an accident

Every payload is hashed into the committed manifest, and the loader refuses to run when a
hash does not match (see `corpus.py`). That guarantee is only worth something if writing
the same data twice produces the same bytes, so:

  * keys are sorted, separators are fixed, `ensure_ascii=False`
  * files are opened with `newline="\\n"` — Windows is the primary dev platform here and
    the default text mode would rewrite every `\\n` to `\\r\\n`, changing the digest of an
    otherwise identical payload
  * the drawing's `id` is preserved verbatim, because the title-block OCR cache is keyed
    on `(drawing_id, file_hash)`; a synthetic id would miss that cache and turn an
    "offline" eval run into a live Gemini call
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

# The payload schema, independent of `EXTRACTION_SCHEMA_VERSION`. Bump when the *file*
# layout changes such that an existing payload can no longer be read the same way — which
# invalidates every recorded sha256, and therefore the whole manifest.
PAYLOAD_SCHEMA_VERSION = 1

_JSON_ARGS: dict[str, Any] = {
    "ensure_ascii": False,
    "sort_keys": True,
    "separators": (",", ":"),
}


class EvalEntity:
    """A stand-in for `ExtractedEntity`, carrying only what the differ reads.

    `__slots__` rather than a dataclass: a corpus pair is ~1200 of these and the harness
    holds every pair in memory during a sweep.
    """

    __slots__ = (
        "entity_type",
        "layer",
        "handle",
        "parent_handle",
        "space",
        "viewport_index",
        "properties",
        "geometry",
        "id",
    )

    def __init__(
        self,
        entity_type: str,
        layer: str = "0",
        handle: str | None = None,
        parent_handle: str | None = None,
        space: str = "model",
        viewport_index: int = -1,
        properties: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
        id: str | None = None,  # noqa: A002 - mirrors the Beanie attribute name
    ) -> None:
        # A sixth attribute the differ reads, discovered by running it: `detect_balloons`
        # (`bom/row_extractor.py:58,77,122`) does `str(entity.id)` to stamp `entity_id` on
        # a balloon finding. The staged plan's "the differ only touches entity_type, layer,
        # handle, properties, geometry" was off by one, and nothing surfaced it because
        # every previous caller passed a Beanie Document. Not persisted — `entities_from_jsonl`
        # derives it from the payload position, so it agrees with a label's address.
        self.id = id if id is not None else (handle or "")
        self.entity_type = entity_type
        self.layer = layer
        self.handle = handle
        self.parent_handle = parent_handle
        self.space = space
        self.viewport_index = viewport_index
        # Never None: 71 call sites in the comparison package do `e.properties.get(...)`
        # without a guard, having only ever seen a Beanie default_factory dict.
        self.properties = properties if properties is not None else {}
        self.geometry = geometry if geometry is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "layer": self.layer,
            "handle": self.handle,
            "parent_handle": self.parent_handle,
            "space": self.space,
            "viewport_index": self.viewport_index,
            "properties": self.properties,
            "geometry": self.geometry,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalEntity:
        return cls(
            entity_type=str(raw.get("entity_type") or ""),
            layer=str(raw.get("layer") if raw.get("layer") is not None else "0"),
            handle=raw.get("handle") or None,
            parent_handle=raw.get("parent_handle") or None,
            space=str(raw.get("space") or "model"),
            viewport_index=int(raw.get("viewport_index", -1)),
            properties=raw.get("properties") or {},
            geometry=raw.get("geometry") or {},
        )

    @classmethod
    def from_document(cls, doc: Any) -> EvalEntity:
        """Adapt anything with the extraction attribute surface — a Beanie
        `ExtractedEntity`, a raw Mongo dict, or a `DXFParser` output dict."""
        if isinstance(doc, dict):
            raw = dict(doc)
            props = raw.get("properties") or {}
            # `setdefault` would be wrong here: a Mongo row has the key `handle` present
            # with value None, so the properties fallback would never fire. The promoted
            # columns are the newer half of the schema and a raw `DXFParser` dict has only
            # the `properties` half, so both shapes have to be accepted.
            for column in ("handle", "parent_handle"):
                if not raw.get(column):
                    raw[column] = props.get(column)
            if raw.get("space") is None:
                raw["space"] = props.get("space", "model")
            if raw.get("viewport_index") is None:
                raw["viewport_index"] = props.get("viewport_index", -1)
            return cls.from_dict(raw)
        return cls(
            entity_type=str(getattr(doc, "entity_type", "") or ""),
            layer=str(getattr(doc, "layer", "0") or "0"),
            handle=getattr(doc, "handle", None),
            parent_handle=getattr(doc, "parent_handle", None),
            space=str(getattr(doc, "space", "model") or "model"),
            viewport_index=int(getattr(doc, "viewport_index", -1) or -1),
            properties=dict(getattr(doc, "properties", None) or {}),
            geometry=dict(getattr(doc, "geometry", None) or {}),
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        text = str(self.properties.get("text") or "")[:24]
        return f"<EvalEntity {self.entity_type} handle={self.handle} {text!r}>"


@dataclass
class EvalDrawing:
    """A stand-in for `DrawingDocument`.

    `id` is a plain `str` holding the original Mongo ObjectId hex. The orchestrator does
    `str(drawing.id)` to build the title-block OCR cache key, so preserving it verbatim is
    what keeps a corpus pair resolvable against `storage/cache/title_block_ocr_v1_*.json`
    and therefore keeps the run offline.
    """

    id: str
    file_name: str
    file_hash: str
    format: str = "dxf"
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)
    entity_counts: dict[str, int] = field(default_factory=dict)
    #: `EXTRACTION_SCHEMA_VERSION` in force when these entities were extracted.
    #:
    #: **0 means unknown, not zero.** Every pair exported before 2026-08-20 lacks the field, so
    #: a corpus payload can be "captured under an extraction nobody recorded" -- which is the
    #: state this exists to stop being possible again.
    #:
    #: It matters because extraction-time fixes are baked into the payload: the v7 note warns
    #: that text captured as ground truth via `EntityAddress.text` is wrong on pre-v7 rows,
    #: where an angular dimension reads `1.05` for a sheet that says `60`-degrees. A label
    #: authored against that is wrong in a way no downstream check can see, and until now the
    #: only way to ask was to read entity values and infer.
    extraction_schema_version: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "format": self.format,
            "status": self.status,
            "metadata": self.metadata,
            "entity_counts": self.entity_counts,
            "extraction_schema_version": self.extraction_schema_version,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalDrawing:
        return cls(
            id=str(raw.get("id") or ""),
            file_name=str(raw.get("file_name") or ""),
            file_hash=str(raw.get("file_hash") or ""),
            format=str(raw.get("format") or "dxf"),
            status=str(raw.get("status") or "completed"),
            metadata=raw.get("metadata") or {},
            entity_counts=raw.get("entity_counts") or {},
            # Absent on every payload written before this field existed. 0 reads as "unknown"
            # everywhere downstream; it must never be presented as a real schema version.
            extraction_schema_version=int(raw.get("extraction_schema_version") or 0),
        )

    @classmethod
    def from_document(cls, doc: Any) -> EvalDrawing:
        if isinstance(doc, dict):
            raw = dict(doc)
            if "id" not in raw and "_id" in raw:
                raw["id"] = str(raw["_id"])
            return cls.from_dict(raw)
        return cls(
            id=str(getattr(doc, "id", "") or ""),
            file_name=str(getattr(doc, "file_name", "") or ""),
            file_hash=str(getattr(doc, "file_hash", "") or ""),
            format=str(getattr(doc, "format", "dxf") or "dxf"),
            status=str(getattr(doc, "status", "completed") or "completed"),
            metadata=dict(getattr(doc, "metadata", None) or {}),
            entity_counts=dict(getattr(doc, "entity_counts", None) or {}),
            extraction_schema_version=int(
                getattr(doc, "extraction_schema_version", 0) or 0
            ),
        )


# ── canonical encoding ────────────────────────────────────────────────────────────────


def _jsonable(value: Any) -> Any:
    """Coerce Mongo-flavoured values into something with a stable JSON encoding.

    Entities extracted from DXF hold plain scalars, but a payload exported out of Mongo
    can pick up a `datetime` or an `ObjectId`. Left unhandled these raise at dump time;
    coerced ad hoc by each caller they would hash differently per caller.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def canonical_json(payload: Any) -> str:
    """The one encoding every hashed artefact in this package goes through."""
    return json.dumps(_jsonable(payload), **_JSON_ARGS)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entities_to_jsonl(entities: Iterable[Any]) -> str:
    """One canonical JSON object per line, trailing newline included.

    JSONL rather than one array so a payload can be streamed and, more usefully, so a
    `git diff` on an accidentally-committed payload is line-oriented.
    """
    lines = [canonical_json(EvalEntity.from_document(e).to_dict()) for e in entities]
    return "".join(f"{line}\n" for line in lines)


def entities_from_jsonl(text: str) -> list[EvalEntity]:
    """Load a payload, stamping each entity with its corpus address as `id`.

    The address is the DXF handle where one exists and `#<line>` where one does not —
    the same two forms an `ExpectedFinding` may use, so a balloon finding's `entity_id`
    and a hand-written label point at the same thing. `id` is derived here rather than
    stored so it can never disagree with the entity's position in the file.
    """
    entities: list[EvalEntity] = []
    for index, line in enumerate(
        [line for line in text.splitlines() if line.strip()]
    ):
        entity = EvalEntity.from_dict(json.loads(line))
        entity.id = entity.handle or f"#{index}"
        entities.append(entity)
    return entities


def write_text_stable(path: Path, text: str) -> str:
    """Write UTF-8 with LF endings and return the sha256 of the bytes written.

    `newline=""` disables Python's newline translation. Without it, the same payload
    written on Windows and on CI would produce two different digests and the manifest
    check would fail for a reason that has nothing to do with the data.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return sha256_text(text)


def read_text_stable(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def iter_entity_dicts(entities: Iterable[Any]) -> Iterator[dict[str, Any]]:
    """Adapter for callers that want the serialized shape without the file."""
    for entity in entities:
        yield EvalEntity.from_document(entity).to_dict()
