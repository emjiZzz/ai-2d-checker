#!/usr/bin/env python
"""Build and inspect the offline evaluation corpus — Stage 0b.

The corpus is the binding constraint on the whole AI maturity ladder: every stage above it
measures against it, and no amount of engine work substitutes for it. See
`docs/vault/00 - AI Maturity Status.md`.

    # register a pair already ingested into the local Mongo
    services/backend/.venv/Scripts/python.exe tools/eval_corpus.py export \
        --pair-id M745200N01 \
        --ref M745200N01_reference.dxf --rev M745200N01_FSRS2_kmti.dxf

    # register a pair straight from two DXF files, no database
    ... tools/eval_corpus.py export-dxf --pair-id FOO --ref a.dxf --rev b.dxf

    ... tools/eval_corpus.py status       # progress against Stage 0b's exit criteria
    ... tools/eval_corpus.py verify       # payload sha256 + offline readiness
    ... tools/eval_corpus.py worksheet --pair-id M745200N01   # annotation aid
    ... tools/eval_corpus.py label --pair-id M745200N01 --from <draft.json>

`worksheet` deliberately does **not** run the comparison engine. A worksheet pre-filled
from engine output would make the engine's own misses invisible to the annotator, and
false negatives are the exact gap this corpus exists to close. It runs a naive,
high-recall text inventory instead — a superset generator, not a differ.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.backend.infrastructure.eval.corpus import (  # noqa: E402
    GUIDELINE_VERSION,
    CorpusError,
    PairLabels,
    PairSide,
    default_fixtures_dir,
    default_payload_dir,
    empty_manifest,
    held_out_access_log,
    load_corpus,
    manifest_path,
    ocr_cache_dir,
    read_manifest,
    write_manifest,
)
from services.backend.infrastructure.eval.serialize import (  # noqa: E402
    EvalDrawing,
    EvalEntity,
    canonical_json,
    entities_to_jsonl,
    read_text_stable,
    write_text_stable,
)
from services.backend.infrastructure.audit.bom.zone_geometry import (  # noqa: E402
    ZONE_POLYGONS_KEY,
    point_in_shape,
    zone_polygons,
)

MONGO_URI_DEFAULT = "mongodb://127.0.0.1:27017"
MONGO_DB_DEFAULT = "ai_2d_checker"


# ── shared helpers ────────────────────────────────────────────────────────────────────


def _load_or_init_manifest() -> dict[str, Any]:
    try:
        return read_manifest()
    except CorpusError:
        return empty_manifest()


def _upsert_pair(manifest: dict[str, Any], entry: dict[str, Any]) -> None:
    pairs = manifest.setdefault("pairs", [])
    for index, existing in enumerate(pairs):
        if existing.get("pair_id") == entry["pair_id"]:
            # Preserve the annotation-side fields; a re-export replaces payload digests,
            # not human work. If the payload actually changed, the labels may no longer be
            # valid — that is why the digest change is printed rather than swallowed.
            entry["labels"] = existing.get("labels")
            entry["label_state"] = existing.get("label_state", entry["label_state"])
            entry["held_out"] = existing.get("held_out", entry["held_out"])
            pairs[index] = entry
            return
    pairs.append(entry)
    pairs.sort(key=lambda p: str(p.get("pair_id")))


def _find_ocr_reading(drawing_id: str, file_hash: str) -> str | None:
    """The cached title-block reading for a drawing, by id or by identical file.

    The by-file-hash fallback matters: **the OCR reading is a function of the drawing file,
    not of the ingestion.** Re-uploading the same DXF mints a new `drawing_id` and therefore
    a new cache key, so an exact-key lookup would miss a reading that is provably for the
    same bytes. That fallback is what makes a reading recoverable at all after the original
    ingestion is deleted.
    """
    cache = ocr_cache_dir()
    exact = cache / f"title_block_ocr_v1_{drawing_id}_{file_hash}.json"
    if exact.exists():
        return read_text_stable(exact)
    for candidate in cache.glob(f"title_block_ocr_v1_*_{file_hash}.json"):
        return read_text_stable(candidate)
    return None


def _write_side(
    pair_id: str,
    side: str,
    drawing: EvalDrawing,
    entities: list[EvalEntity],
    ocr_text: str | None = None,
) -> PairSide:
    from services.backend.domain.models.zone_template import zone_signature

    target = default_payload_dir() / pair_id
    drawing_sha = write_text_stable(
        target / f"{side}.drawing.json", canonical_json(drawing.to_dict())
    )
    entities_sha = write_text_stable(
        target / f"{side}.entities.jsonl", entities_to_jsonl(entities)
    )

    # Capture the title-block OCR reading into the corpus. It used to live only in
    # storage/cache/, outside the sha256-pinned payloads — so deleting old comparisons
    # removed it and the engine silently fell back to spatial title extraction on one side
    # while the other still had a reading. The corpus now owns it.
    if ocr_text is None:
        ocr_text = _find_ocr_reading(drawing.id, drawing.file_hash)
    ocr_sha = ""
    if ocr_text is not None:
        ocr_sha = write_text_stable(target / f"{side}.ocr.json", ocr_text)

    return PairSide(
        drawing_id=drawing.id,
        file_name=drawing.file_name,
        file_hash=drawing.file_hash,
        drawing_sha256=drawing_sha,
        entities_sha256=entities_sha,
        entity_count=len(entities),
        # Pure function of render_bounds, so it is recorded without needing a database.
        zone_signature=zone_signature(drawing.metadata.get("render_bounds") or []) or "",
        ocr_sha256=ocr_sha,
    )


def _register(
    pair_id: str,
    ref: PairSide,
    rev: PairSide,
    *,
    provenance: str,
    held_out: bool,
    notes: str,
) -> None:
    manifest = _load_or_init_manifest()
    manifest["guideline_version"] = GUIDELINE_VERSION
    _upsert_pair(
        manifest,
        {
            "pair_id": pair_id,
            "provenance": provenance,
            "held_out": held_out,
            "label_state": "unlabelled",
            "labels": None,
            "notes": notes,
            "ref": ref.to_dict(),
            "rev": rev.to_dict(),
        },
    )
    path = write_manifest(manifest)
    print(f"  manifest: {path}")
    print(f"  payloads: {default_payload_dir() / pair_id}")
    _report_ocr_readiness(pair_id, ref, rev)


def _report_ocr_readiness(pair_id: str, ref: PairSide, rev: PairSide) -> None:
    """Warn when a pair would fire a live Gemini call.

    `generate_deterministic_candidates` is not network-free: on a title-block OCR cache
    miss it calls Gemini. A corpus pair without its two cache files silently breaks the
    "zero network calls" exit criterion, so this is checked at export time, not discovered
    during a sweep.
    """
    missing = [
        side.ocr_cache_filename()
        for side in (ref, rev)
        if not (ocr_cache_dir() / side.ocr_cache_filename()).exists()
    ]
    if missing:
        print(
            f"  [warn] {pair_id}: {len(missing)} title-block OCR cache file(s) missing - an eval "
            f"run on this pair would make a live Gemini call, or fall back to spatial "
            f"heuristics and produce different title-block findings:"
        )
        for name in missing:
            print(f"      {name}")
    else:
        print(f"  [ok] {pair_id}: title-block OCR cached for both sides (offline-ready)")


# ── commands ──────────────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    path = manifest_path()
    if path.exists() and not args.force:
        print(f"Manifest already exists at {path} (use --force to reset).")
        return 0
    write_manifest(empty_manifest())
    (default_fixtures_dir() / "labels").mkdir(parents=True, exist_ok=True)
    print(f"Initialised empty corpus manifest at {path}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export a pair from the local Mongo, preserving drawing ids and file hashes."""
    from pymongo import MongoClient

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[args.mongo_db]

    def resolve(ref: str) -> dict[str, Any]:
        query: dict[str, Any] = {"file_name": ref}
        matches = list(db["drawing_documents"].find(query))
        if not matches:
            from bson import ObjectId

            try:
                doc = db["drawing_documents"].find_one({"_id": ObjectId(ref)})
            except Exception:
                doc = None
            if doc:
                return doc
            raise SystemExit(f"No drawing matches {ref!r} by file_name or _id.")
        if len(matches) > 1:
            ids = ", ".join(str(m["_id"]) for m in matches)
            raise SystemExit(
                f"{len(matches)} drawings share file_name {ref!r} ({ids}). Pass the _id "
                f"instead - a corpus pair must name exactly one extraction."
            )
        return matches[0]

    sides: dict[str, PairSide] = {}
    for side, reference in (("ref", args.ref), ("rev", args.rev)):
        doc = resolve(reference)
        drawing_id = str(doc["_id"])
        drawing = EvalDrawing.from_document({**doc, "id": drawing_id})
        rows = list(db["extracted_entities"].find({"drawing_id": drawing_id}))
        if not rows:
            raise SystemExit(
                f"{reference!r} ({drawing_id}) has no extracted entities. Re-ingest it "
                f"before adding it to the corpus."
            )
        entities = [EvalEntity.from_document(row) for row in rows]
        if not drawing.metadata.get("render_bounds"):
            print(
                f"  [warn] {side}: no render_bounds in metadata - zone templates are stored as "
                f"fractions of it, so zone detection will behave differently here than in "
                f"the app."
            )
        sides[side] = _write_side(args.pair_id, side, drawing, entities)
        print(f"  {side}: {drawing.file_name} ({len(entities)} entities, id={drawing_id})")

    _register(
        args.pair_id,
        sides["ref"],
        sides["rev"],
        provenance=args.provenance,
        held_out=args.held_out,
        notes=args.notes,
    )
    return 0


def cmd_export_dxf(args: argparse.Namespace) -> int:
    """Export a pair straight from two DXF files — no database, no ingestion run."""
    from services.backend.infrastructure.cad.dxf_parser import DXFParser

    parser = DXFParser()
    sides: dict[str, PairSide] = {}
    for side, path_str in (("ref", args.ref), ("rev", args.rev)):
        path = Path(path_str).resolve()
        if not path.exists():
            raise SystemExit(f"{side}: {path} does not exist.")
        raw_entities, layers, counts, metadata = parser.parse_file(path)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        # A synthetic but stable id. It keys the title-block OCR cache, so it must not
        # change between exports of the same file — hence deriving it from the hash rather
        # than minting a fresh ObjectId.
        drawing_id = f"dxf{file_hash[:22]}"

        if args.render:
            # Same call ingestion makes. It is what populates `render_bounds` and writes
            # the PNG that `crop_title_block_image` needs, so a rendered DXF pair behaves
            # like an ingested one rather than like a subtly different third thing.
            from services.backend.infrastructure.rendering.dxf_background_renderer import (
                render_dxf_background,
            )

            render_dxf_background(path, drawing_id, metadata, raw_entities)

        if not metadata.get("render_bounds"):
            print(
                f"  [warn] {side}: no render_bounds - pass --render (needs matplotlib) or expect "
                f"zone detection to diverge from the app's behaviour on this pair."
            )

        drawing = EvalDrawing(
            id=drawing_id,
            file_name=path.name,
            file_hash=file_hash,
            format=path.suffix.lstrip(".").lower() or "dxf",
            metadata=metadata,
            entity_counts=counts,
        )
        entities = [EvalEntity.from_document(item) for item in (layers + raw_entities)]
        sides[side] = _write_side(args.pair_id, side, drawing, entities)
        print(f"  {side}: {path.name} ({len(entities)} entities, id={drawing_id})")

    _register(
        args.pair_id,
        sides["ref"],
        sides["rev"],
        provenance=args.provenance,
        held_out=args.held_out,
        notes=args.notes,
    )
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    """Generate mutation pairs from a registered base pair.

    A mutation pair is the base drawing plus a deliberately edited copy, so its labels are
    known by construction — no annotator, and as many pairs as wanted. See
    `infrastructure/eval/mutator.py` for what each operator does and, more importantly,
    for the three that are designed to produce *no* finding.
    """
    from services.backend.infrastructure.eval.mutator import (
        MUTATION_SCHEMA_VERSION,
        ZERO_FINDING_OPERATORS,
        Mutator,
        ocr_cache_payload,
    )

    corpus = _load_for_management()
    base = corpus.by_id(args.base)
    if base is None:
        raise SystemExit(f"No base pair {args.base!r} in the corpus. Export it first.")

    ref_drawing, rev_drawing, ref_entities, rev_entities = base.load()
    side = args.side
    base_drawing = ref_drawing if side == "ref" else rev_drawing
    base_entities = ref_entities if side == "ref" else rev_entities
    base_meta = base.ref if side == "ref" else base.rev

    ocr_path = ocr_cache_dir() / base_meta.ocr_cache_filename()
    base_ocr = json.loads(read_text_stable(ocr_path)) if ocr_path.exists() else None
    if base_ocr is None:
        print(
            f"  [warn] no title-block OCR cache for the base side - title_block mutations "
            f"will be skipped, since a label the engine cannot satisfy is worse than no "
            f"label. Expected at {ocr_path}"
        )

    # The mutator must scope with the same zone boxes the engine will, or the categories it
    # writes into the labels describe a different sheet layout than the one under test.
    # `base_meta.zone_template` is None when the sheet has never been captured, which keeps
    # the old detection-only behaviour rather than guessing.
    if base_meta.zone_template is None:
        print(
            f"  [warn] sheet '{base_meta.zone_signature}' has no captured zone template, so "
            f"these labels will be scoped by plain detection while the engine may use a "
            f"pinned one. Run: eval_corpus.py capture-zones --pair-id {args.base}"
        )
    mutator = Mutator(base_drawing, base_entities, base_ocr, base_meta.zone_template)
    manifest = _load_or_init_manifest()
    generated = 0
    zero_finding_pairs = 0

    for index in range(args.count):
        seed = args.seed + index
        pair_id = f"{args.base}-{side}-{args.tag}{index:03d}"
        pair = mutator.generate(
            pair_id,
            seed=seed,
            operators=args.operators.split(",") if args.operators else None,
            edits=args.edits,
        )

        target = default_payload_dir() / pair_id
        # The reference side is the untouched base, byte-identical to what it was exported
        # as, so a mutation pair differs from its base in exactly the edits applied.
        # Both readings are captured into the pair, not merely written to the cache: the
        # base side's so it survives a cache wipe, the mutated side's because it is derived
        # and exists nowhere else.
        derived_ocr = ocr_cache_payload(pair)
        ref_side = _write_side(
            pair_id,
            "ref",
            base_drawing,
            base_entities,
            ocr_text=json.dumps(base_ocr, ensure_ascii=False, indent=2) if base_ocr else None,
        )
        rev_side = _write_side(pair_id, "rev", pair.drawing, pair.entities, ocr_text=derived_ocr)

        labels = {
            "pair_id": pair_id,
            "guideline_version": GUIDELINE_VERSION,
            "annotator": f"mutator v{MUTATION_SCHEMA_VERSION}",
            "annotated_at": datetime.now(UTC).date().isoformat(),
            "notes": "; ".join(pair.applied) or "null_mutation",
            "findings": [f.to_dict() for f in pair.findings],
            "not_findings": [],
        }
        labels_sha = write_text_stable(
            target / "labels.json", json.dumps(labels, ensure_ascii=False, indent=2) + "\n"
        )

        # The derived OCR entry, so the mutated side resolves its own cache rather than
        # firing a live Gemini call or falling back to spatial heuristics.
        if derived_ocr is not None:
            write_text_stable(ocr_cache_dir() / rev_side.ocr_cache_filename(), derived_ocr)

        _upsert_pair(
            manifest,
            {
                "pair_id": pair_id,
                "provenance": "mutation",
                "held_out": False,
                "label_state": "labelled",
                "labels": None,
                "labels_sha256": labels_sha,
                "notes": f"generated from {args.base} ({side} side)",
                "ref": ref_side.to_dict(),
                "rev": rev_side.to_dict(),
                "mutation": {
                    "schema_version": MUTATION_SCHEMA_VERSION,
                    "base_pair_id": args.base,
                    "base_side": side,
                    "seed": seed,
                    "operators_applied": pair.applied,
                    "operators_rejected": pair.rejected,
                    "zero_finding": pair.is_null_pair,
                },
                "finding_count": len(pair.findings),
            },
        )
        generated += 1
        if pair.is_null_pair:
            zero_finding_pairs += 1
        if args.verbose:
            print(f"  {pair.summary()}")

    manifest["guideline_version"] = GUIDELINE_VERSION
    write_manifest(manifest)
    print(
        f"Generated {generated} mutation pair(s) from {args.base} ({side} side), "
        f"{zero_finding_pairs} of them zero-finding."
    )
    print(
        "  Zero-finding pairs measure precision only - every finding an engine reports on "
        f"one is a false positive. Operators: {sorted(ZERO_FINDING_OPERATORS)}"
    )
    print(
        "  Generated labels are NOT committed. The manifest carries the seed and operator "
        "list that reproduces them, which is smaller and cannot disagree with itself."
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    corpus = _load_for_management(
        include_held_out=True,
        held_out_reason="integrity verification — no engine output is read",
    )
    failures = 0
    for pair in corpus.pairs:
        try:
            pair.verify()
        except CorpusError as exc:
            failures += 1
            print(f"[FAIL] {pair.pair_id}\n  {exc}")
            continue
        missing = pair.missing_ocr_cache()
        flag = "held-out" if pair.held_out else pair.provenance
        note = f"  [warn] {len(missing)} OCR cache file(s) missing" if missing else ""
        print(f"[ok] {pair.pair_id} [{flag}, {pair.label_state}]{note}")
        for signature in pair.zone_template_risk():
            pinned = _pinned_template_exists(signature)
            if pinned is not False:
                print(
                    f"       [warn] sheet '{signature}'"
                    + (" has a pinned zone template" if pinned else " may have a pinned template")
                    + " that an offline run cannot resolve - its zone boxes will differ"
                    " from the app's. Run: eval_corpus.py capture-zones"
                    f" --pair-id {pair.pair_id}"
                )
    if failures:
        print(f"\n{failures} pair(s) failed integrity verification.")
    return 1 if failures else 0


def _resolve_template_zones(db: Any, signature: str) -> dict[str, Any]:
    """The zone fractions the app would apply to this sheet, as a plain dict.

    Mirrors `resolve_zone_overrides`' lookup order exactly — signature-specific first, then
    the global default — because a capture that resolved differently from the app would
    substitute one divergence for another. Returns `{}` when nothing is pinned, which is a
    real answer and is stored as such.
    """
    template = db["zone_templates"].find_one({"signature": signature}) if signature else None
    if not template:
        template = db["zone_templates"].find_one({"is_default": True})
    if not template:
        return {}
    return {
        key: value
        for key, value in (template.get("zones") or {}).items()
        if isinstance(value, dict)
    }


def _load_for_management(**kwargs: Any):
    """Load the corpus for a command that inspects or *rewrites* labels.

    Tolerates a stale `guideline_version`, and says so. The strict check belongs on the path
    where a stale label would corrupt a number — `tools/eval.py`, which keeps it — not on the
    commands you need in order to *fix* the staleness. Without this the guard blocks its own
    remedy: bumping the version makes `mutate` unable to load the corpus whose labels it is
    about to regenerate, and `verify`/`status` unable to report what needs regenerating.
    """
    corpus = load_corpus(allow_stale_guideline=True, **kwargs)
    stale = sorted(
        p.pair_id
        for p in corpus.pairs
        if p.labels is not None and p.labels.guideline_version != GUIDELINE_VERSION
    )
    if stale:
        print(
            f"  [warn] {len(stale)} pair(s) labelled under an older guideline than "
            f"{GUIDELINE_VERSION}; `tools/eval.py` will refuse them until they are "
            f"regenerated or re-labelled: {', '.join(stale[:4])}"
            + (f" (+{len(stale) - 4} more)" if len(stale) > 4 else "")
        )
    return corpus


def cmd_capture_zones(args: argparse.Namespace) -> int:
    """Freeze each side's hand-aligned zone template into the manifest.

    Zone boxes decide what `drawing_views` contains and what the safe zones exclude
    entirely, so an offline run that cannot reach Mongo was silently scoring against
    different boxes than the app uses. Capturing the fractions makes the zone boxes a
    property of the corpus. See the vault gotcha "Zone Templates Vanish in Offline Eval".
    """
    from pymongo import MongoClient

    db = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)[args.mongo_db]
    manifest = _load_or_init_manifest()
    captured: dict[str, dict[str, Any]] = manifest.get("zone_templates") or {}

    # Keyed by sheet signature, not by side. A zone template is a property of the sheet
    # layout, so every pair of the same layout shares one entry — writing it per side put
    # the identical block in the manifest 74 times.
    wanted: dict[str, list[str]] = {}
    for entry in manifest.get("pairs", []):
        if args.pair_id and entry.get("pair_id") != args.pair_id:
            continue
        for side in ("ref", "rev"):
            signature = str((entry.get(side) or {}).get("zone_signature") or "")
            if not signature:
                continue
            wanted.setdefault(signature, []).append(f"{entry.get('pair_id')}/{side}")

    fresh = 0
    for signature, users in sorted(wanted.items()):
        if signature in captured and not args.force:
            print(f"  {signature}: already captured ({len(users)} side(s)) - skipped")
            continue
        zones = _resolve_template_zones(db, signature)
        captured[signature] = zones
        fresh += 1
        print(
            f"  {signature}: "
            + (f"{len(zones)} pinned zone(s) {sorted(zones)}" if zones else "no template")
            + f" -> {len(users)} side(s)"
        )

    if not fresh:
        print("\nNothing to capture — every sheet already has its template (--force to redo).")
        return 0

    manifest["zone_templates"] = captured
    path = write_manifest(manifest)
    print(f"\nCaptured {fresh} sheet layout(s). Manifest: {path}")
    print("The baseline moves: the engine now applies these boxes offline. Re-publish it.")
    return 0


def _pinned_template_exists(signature: str) -> bool | None:
    """True/False when Mongo can be reached, None when it cannot.

    None is not "no template" — it is "unknown", and the caller warns either way. Treating
    an unreachable database as an absence is how this divergence stays invisible.
    """
    try:
        from pymongo import MongoClient

        db = MongoClient(MONGO_URI_DEFAULT, serverSelectionTimeoutMS=1500)[MONGO_DB_DEFAULT]
        return bool(
            db["zone_templates"].find_one({"$or": [{"signature": signature}, {"is_default": True}]})
        )
    except Exception:
        return None


def cmd_status(args: argparse.Namespace) -> int:
    corpus = _load_for_management()
    report = corpus.status_report()
    print("Stage 0b - human corpus (needs an annotator)\n")
    print(f"  human pairs        {report['human_pairs']:>3} / {report['human_pairs_required']}")
    print(
        f"  of those labelled  {report['labelled_human_pairs']:>3} / "
        f"{report['human_pairs_required']}"
    )
    print(f"  held out           {report['held_out']:>3} / {report['held_out_required']}")
    print(f"\n  stage 0b complete: {report['stage_0b_complete']}")
    print("\nStage 0c - mutation corpus (labelled by construction)\n")
    print(
        f"  mutation pairs     {report['mutation_pairs']:>3} / "
        f"{report['mutation_pairs_required']}"
    )
    print(
        f"  of those zero-finding {report['zero_finding_pairs']:>3}"
        "   (pure precision probes)"
    )
    print(f"\n  stage 0c complete: {report['stage_0c_complete']}")
    if report["burned_pairs"]:
        print(f"\n  BURNED (used for tuning, must be replaced): {report['burned_pairs']}")

    # Per-pair queue. The aggregate above says how much is left; this says what to open next,
    # which is the question an annotator actually has. Human pairs only — the 36 mutation pairs
    # are labelled by construction and listing them would bury the six that need a person.
    human = [p for p in corpus.pairs if p.provenance == "human"]
    if human:
        print("\n  Annotation queue (human pairs)\n")
        for pair in sorted(human, key=lambda p: p.pair_id):
            if pair.labels is None:
                state = "UNLABELLED"
            elif pair.labels.guideline_version != GUIDELINE_VERSION:
                state = f"STALE ({pair.labels.guideline_version})"
            else:
                state = f"labelled  {len(pair.labels.findings):>3} finding(s)"
            flag = "  [held out]" if pair.held_out else ""
            print(f"    {pair.pair_id:<14} {state}{flag}")
        hidden = report["human_pairs"] - len(human)
        if hidden > 0:
            # Not a discrepancy: held-out pairs load only with an explicit reason, which is the
            # lock working. Said out loud so the count above does not read as a bug.
            print(
                f"\n    ({hidden} held-out pair(s) not listed — they load only with "
                f"--include-held-out and a --reason, which is logged.)"
            )

    log = held_out_access_log()
    if log.exists():
        lines = [line for line in read_text_stable(log).splitlines() if line.strip()]
        print(f"\n  held-out access log: {len(lines)} entr(y/ies) at {log}")
    return 0


def require_named_annotator(raw: str, session_id: str) -> str:
    """The annotator, or refuse. Ground truth is attributable work.

    Two rejections, not one. Emptiness is the obvious case and `label` would catch it downstream
    anyway; **`"unknown"` is the one that mattered**, and it used to pass straight through.

    It is not a name an annotator can enter. It is the literal fallback `create_session` writes
    when a manual check is opened with no `X-Session-Token` -- an app that is running but not
    signed in. A check-for-empty does not catch it, so it reached a committed label file as the
    `annotator`, where it is indistinguishable from a person and there is no other record of who
    did the work.

    Extracted from `cmd_from_manual_check` so the rule is testable without a Mongo connection
    and a loaded corpus pair, the same way `_require_category` sits apart from its route.
    """
    annotator = raw.strip()
    if not annotator:
        raise SystemExit(
            "The session names no annotator and --annotator was not given. Ground truth is "
            "attributable work; `label` would refuse this draft anyway."
        )
    if annotator.lower() == "unknown":
        raise SystemExit(
            f"Session {session_id} is attributed to 'unknown' -- it was opened without a "
            "signed-in user, so the server could not name the annotator. Ground truth has to be "
            "attributable to a person. Pass --annotator <name> to say who did this check."
        )
    return annotator


def _print_bridge_summary(pair_id: str, session_id: str, live: int, result: Any) -> None:
    """What the conversion did, in the terms a reviewer needs before installing.

    Split out of `cmd_from_manual_check` because the command was doing two jobs: deciding what
    converts, and explaining it. The counts here are the only place an annotator learns that
    their N markings became fewer than N labels.
    """
    print(f"\n{pair_id} <- session {session_id}")
    print(f"  live markings      {live}")
    print(f"  -> findings        {len(result.labels.findings)}")
    print(f"  -> not_findings    {len(result.labels.not_findings)}")
    if result.tier_counts:
        tiers = ", ".join(f"{k} {v}" for k, v in sorted(result.tier_counts.items()))
        print(f"  resolved by        {tiers}")
    if result.labels.findings:
        print(
            f"  handle-anchored    {result.labels.handle_anchored_count}"
            f" / {len(result.labels.findings)}"
        )
        for category, count in sorted(result.labels.category_counts.items()):
            if count:
                print(f"    {category}: {count}")
    if result.zone_derived:
        print(
            f"\n  [warn] {result.zone_derived} finding(s) carry a zone-derived category, "
            f"tagged `[category:zone]` in their notes.\n"
            f"         Attribution measured over these is circular -- it compares "
            f"zone_detector with itself.\n"
            f"         Review them before installing; see manual_check_bridge.py."
        )


def cmd_from_manual_check(args: argparse.Namespace) -> int:
    """Convert a Manual Check session into a corpus label draft.

    The bridge between this project's two ground-truth stores. The app writes
    `ground_truth_markings` to Mongo; Stage 0b counts only `tests/fixtures/eval/labels/`. An
    engineer using the only UI that exists was therefore producing work that `status` could not
    see -- measured 2026-08-20 at three sessions and 7 live markings against a corpus reading
    4 / 8.

    **This writes a draft and stops.** Installing is still `label`, which still demands a named
    annotator and a current guideline version. The conversion is lossy in ways only a person can
    adjudicate -- see `infrastructure/eval/manual_check_bridge.py` for exactly where -- so the
    draft is a proposal to review, not a result to trust.
    """
    from bson import ObjectId
    from pymongo import MongoClient

    from services.backend.infrastructure.eval.manual_check_bridge import (
        build_labels,
        check_session_matches_pair,
    )

    corpus = _load_for_management(
        include_held_out=args.include_held_out,
        held_out_reason=args.reason,
    )
    pair = corpus.by_id(args.pair_id)
    if pair is None:
        raise SystemExit(
            f"No pair {args.pair_id!r} in the loaded corpus. Held-out pairs need "
            f"--include-held-out with a --reason."
        )

    # Defaults to the app's configured MONGO_URI, NOT this tool's localhost default. Measured
    # 2026-08-20: local Mongo holds 0 manual-check sessions and 0 markings while Atlas holds 3
    # and 38 — those two collections are not in `sync_manager`'s synced set. `export` is right
    # to default to local (payloads are exported from whatever store you point it at); this
    # command is only ever reading what the running app wrote, so its default follows the app.
    uri = args.mongo_uri
    if not uri:
        from services.backend.config import settings

        uri = settings.MONGO_URI
    db = MongoClient(uri, serverSelectionTimeoutMS=8000)[args.mongo_db]
    sessions = db["manual_check_sessions"]
    markings = db["ground_truth_markings"]
    drawings = db["drawing_documents"]

    def file_hashes(session_doc: dict[str, Any]) -> tuple[str, str]:
        """`(ref_hash, rev_hash)` for a session's two drawings, empty where not found."""
        out = []
        for key in ("ref_drawing_id", "rev_drawing_id"):
            doc = None
            try:
                doc = drawings.find_one({"_id": ObjectId(str(session_doc.get(key)))})
            except Exception:  # noqa: BLE001 - a bad id is simply an absent hash
                doc = None
            out.append(str((doc or {}).get("file_hash") or ""))
        return out[0], out[1]

    # Without an explicit session, offer the ones that actually describe this pair rather than
    # making the caller hunt ObjectIds. Matching on both drawing ids is the same check that
    # guards the conversion below, so the list can never suggest a session it would then refuse.
    if not args.session_id:
        candidates = []
        for doc in sessions.find({}):
            ref_hash, rev_hash = file_hashes(doc)
            problems, _ = check_session_matches_pair(
                pair,
                ref_drawing_id=str(doc.get("ref_drawing_id")),
                rev_drawing_id=str(doc.get("rev_drawing_id")),
                ref_file_hash=ref_hash,
                rev_file_hash=rev_hash,
            )
            if not problems:
                candidates.append(doc)
        if not candidates:
            raise SystemExit(
                f"No manual-check session covers {args.pair_id} "
                f"(ref {pair.ref.drawing_id}, rev {pair.rev.drawing_id}). "
                f"A session must name the same two drawings the pair was exported from."
            )
        print(f"Sessions covering {args.pair_id}:\n")
        for doc in candidates:
            live = markings.count_documents(
                {"session_id": str(doc["_id"]), "retracted_at": None}
            )
            print(
                f"  {doc['_id']}  annotator={doc.get('annotator')!r} "
                f"status={doc.get('status')!r} live_markings={live}"
            )
        print("\nRe-run with --session-id <id>.")
        return 1

    session = sessions.find_one({"_id": ObjectId(args.session_id)})
    if session is None:
        raise SystemExit(f"No manual-check session {args.session_id!r}.")

    ref_hash, rev_hash = file_hashes(session)
    problems, identity_notes = check_session_matches_pair(
        pair,
        ref_drawing_id=str(session.get("ref_drawing_id")),
        rev_drawing_id=str(session.get("rev_drawing_id")),
        ref_file_hash=ref_hash,
        rev_file_hash=rev_hash,
    )
    if problems:
        raise SystemExit(
            "This session does not describe this pair:\n  "
            + "\n  ".join(problems)
            + "\n\nLabels attached to the wrong pair resolve against the wrong payload and "
            "read as perfectly ordinary ground truth. Refusing."
        )
    for note in identity_notes:
        # Not a warning: a re-upload is the normal case, and the pair's payload is frozen by
        # sha256 regardless of which DrawingDocument it came from. Printed so the caller can
        # see which extraction the markings were authored against.
        print(f"  [note] {note}")

    # `retracted_at: None` is applied in the query as well as in the bridge. Belt and braces on
    # purpose: 31 of the 38 markings in the session that prompted this feature are retracted,
    # so a converter that let them through would manufacture findings the engineer took back.
    live = list(markings.find({"session_id": args.session_id, "retracted_at": None}))
    if not live:
        raise SystemExit(
            f"Session {args.session_id} has no live markings "
            f"(retracted ones do not count). Nothing to convert."
        )

    _, _, ref_entities, rev_entities = pair.load()

    annotator = require_named_annotator(
        args.annotator or session.get("annotator") or "", args.session_id
    )

    dates = sorted(str(m.get("created_at") or "")[:10] for m in live if m.get("created_at"))
    annotated_at = dates[-1] if dates and dates[-1] else datetime.now(UTC).date().isoformat()

    provenance = (
        f"Converted from manual-check session {args.session_id} "
        f"({len(live)} live marking(s), annotator {annotator!r})."
    )
    session_notes = str(session.get("notes") or "").strip()

    result = build_labels(
        pair_id=pair.pair_id,
        markings=live,
        ref_entities=ref_entities,
        rev_entities=rev_entities,
        annotator=annotator,
        annotated_at=annotated_at,
        notes=f"{provenance} {session_notes}".strip(),
    )

    _print_bridge_summary(args.pair_id, args.session_id, len(live), result)

    if result.unresolved:
        print(f"\n  [!] {len(result.unresolved)} marking(s) did NOT convert:")
        for item in result.unresolved:
            text = f" {item.text[:36]!r}" if item.text else ""
            print(f"      {item.marking_id} {item.status}/{item.category}{text}")
            print(f"        {item.reason}")
        if not args.allow_unresolved:
            raise SystemExit(
                "\nRefusing to write a partial draft. Every unconverted marking is a human "
                "judgement that would silently not be in the corpus, and the draft gives no "
                "hint that it is short. Fix the addresses, or pass --allow-unresolved to "
                "accept the loss deliberately."
            )
        print("\n  [warn] --allow-unresolved: writing anyway, short by the rows above.")

    out_dir = default_payload_dir().parent / "worksheets"
    # A distinct filename from `worksheet`'s own draft. Overwriting that silently would destroy
    # hand-annotation with machine output, and the provenance belongs in the name.
    draft_path = Path(args.out) if args.out else (
        out_dir / f"{pair.pair_id}.from-manual-check.labels.draft.json"
    )
    if draft_path.exists() and not args.force:
        raise SystemExit(f"{draft_path} exists. Pass --force to overwrite.")
    write_text_stable(
        draft_path, json.dumps(result.labels.to_dict(), ensure_ascii=False, indent=2) + "\n"
    )
    print(f"\n  draft: {draft_path}")
    print(
        f"\nReview it, then:\n"
        f"  tools/eval_corpus.py validate --pair-id {pair.pair_id} --from {draft_path}\n"
        f"  tools/eval_corpus.py label    --pair-id {pair.pair_id} --from {draft_path}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Check a draft in place, without installing it.

    The loop before this was fill -> `label --from` -> rejection, with no way to check work in
    progress; a malformed address found after an hour of annotation cost that hour. This runs
    the same `PairLabels.from_dict` the installer runs, plus address resolution against the
    frozen payload, and reports every problem at once rather than the first.

    Deliberately read-only: it never writes the manifest and never installs. `label` is still
    the only command that changes ground truth.
    """
    source = Path(args.source).resolve()
    if not source.exists():
        raise SystemExit(f"{source} does not exist.")

    problems: list[str] = []
    try:
        raw = json.loads(read_text_stable(source))
    except json.JSONDecodeError as err:
        raise SystemExit(f"[fail] {source.name} is not valid JSON: {err}")

    raw.setdefault("pair_id", args.pair_id)
    if not str(raw.get("annotator") or "").strip():
        problems.append("`annotator` is empty — required before this can be installed.")

    labels = None
    try:
        # Version drift is reported as its own problem rather than aborting, so an annotator
        # working against an older guideline still gets the rest of their errors in one pass.
        labels = PairLabels.from_dict(raw, allow_stale_guideline=True)
    except Exception as err:
        problems.append(f"schema: {err}")

    if labels is not None:
        if labels.guideline_version != GUIDELINE_VERSION:
            problems.append(
                f"guideline_version is {labels.guideline_version!r}, current is "
                f"{GUIDELINE_VERSION!r}. `tools/eval.py` will refuse these labels. Re-generate "
                f"the worksheet (--force) and re-check the rules that changed."
            )
        if not labels.findings:
            problems.append(
                "zero findings — legitimate only for a null_mutation pair; on a human pair it "
                "usually means the draft is not filled in yet."
            )

        corpus = _load_for_management()
        pair = corpus.by_id(args.pair_id)
        if pair is None:
            problems.append(f"no pair {args.pair_id!r} in the manifest — export it first.")
        else:
            try:
                _, _, ref_entities, rev_entities = pair.load()
            except Exception as err:
                problems.append(f"payload unreadable, addresses not checked: {err}")
            else:
                known = _addressable(ref_entities, rev_entities)
                for index, finding in enumerate(labels.findings):
                    address = getattr(finding, "entity_handle", None)
                    if address and address not in known:
                        problems.append(
                            f"findings[{index}]: address {address!r} resolves to no entity on "
                            f"either side. Copy it verbatim from the worksheet's `address` "
                            f"column."
                        )

    if problems:
        print(f"[fail] {args.pair_id}: {len(problems)} problem(s)\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"[ok] {args.pair_id}: {len(labels.findings)} finding(s) — this draft will install.\n"
        f"     tools/eval_corpus.py label --pair-id {args.pair_id} --from {source}"
    )
    return 0


def _addressable(ref_entities: list, rev_entities: list) -> set[str]:
    """Every address form the worksheet emits, for both sides.

    Mirrors `cmd_worksheet.address` exactly — handle when one exists, payload line number
    otherwise. If the two ever disagree the worksheet would print addresses this rejects.
    """
    known: set[str] = set()
    for side, entities in (("REF", ref_entities), ("REV", rev_entities)):
        for index, entity in enumerate(entities):
            known.add(f"{side}-{entity.handle}" if entity.handle else f"{side}#{index}")
    return known


# Per the annotation guideline, "Safe zones are never compared" — a difference inside one is not
# a finding, so a worksheet row landing there is guaranteed noise for the annotator.
SAFE_ZONES = frozenset({"tolerance"})

# Bucket names used by `triage_row`. 'review' is the only one an annotator must read line by line.
BUCKET_REVIEW, BUCKET_SAFE, BUCKET_NO_ZONE = "review", "safe-zone", "no-zone"


def anchor_of(entity: "EvalEntity") -> list[float]:
    return entity.geometry.get("insert") or entity.geometry.get("location") or []


def _zone_contains(bbox: Any, polygon: Any, anchor: Sequence[float]) -> bool:
    """Containment for one zone shape, tolerating an unordered bbox.

    `point_in_shape` assumes `(xmin, ymin, xmax, ymax)`. The corner order here is not
    guaranteed — the two sides of a pair resolve their fractions against different
    `render_bounds` and a reference sheet may be stored in another coordinate space entirely
    (see `Gotcha - Reference and Revision in Different Coordinate Spaces`) — so the box is
    normalised per axis before the shared helper sees it.
    """
    if not bbox or len(bbox) != 4:
        return False
    x0, y0, x1, y1 = bbox
    normalised = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return point_in_shape(anchor[0], anchor[1], normalised, polygon)


def zones_containing(zone_boxes: dict, anchor: Sequence[float]) -> list[str]:
    """Every template zone whose shape contains `anchor`.

    Returns a list, not a first match, because **hand-drawn zones overlap**: on the live corpus
    `tolerance` ends at x=151.9 and `title` begins at x=151.8. A single-match version would
    resolve that 0.1-unit sliver by dict order, which decides whether a row is excluded or
    reviewed on nothing at all.

    A **reshaped** zone is tested against its outline, not its bounding box. That distinction is
    load-bearing: the engine gates content on the outline (`scope_entities_to_views`,
    `views_exclusions`), so a worksheet reading only the bbox would tell the annotator a row sits
    in a zone the runner actually excludes — the tool and the runner disagreeing about the same
    L-shaped zone, which is precisely the divergence this worksheet exists to surface. The
    outlines ride under the reserved `_zone_polygons` key, which is not itself a zone.
    """
    if len(anchor) < 2:
        return []
    polygons = zone_polygons(zone_boxes)
    return [
        zone_key
        for zone_key, bbox in zone_boxes.items()
        if zone_key != ZONE_POLYGONS_KEY
        and _zone_contains(bbox, polygons.get(zone_key), anchor)
    ]


def zone_containing(zone_boxes: dict, anchor: Sequence[float]) -> str | None:
    """The zone to display for a row. A scored zone wins over a safe one where they overlap."""
    hits = zones_containing(zone_boxes, anchor)
    scored = [z for z in hits if z not in SAFE_ZONES]
    return (scored or hits or [None])[0]


def triage_row(zone_boxes: dict, anchor: Sequence[float]) -> tuple[str, str | None]:
    """`(bucket, zone)` for one worksheet row.

    The only rule that matters here: **this never excludes on uncertainty.** With no template,
    or an entity carrying no usable coordinate, the row goes to `review`. Grouping a row as
    "not a finding" is a claim that the guideline covers it, and a guess is not that claim —
    a wrongly excluded row is a miss the annotator never sees, which is precisely the quantity
    the whole corpus exists to measure.
    """
    if not zone_boxes:
        return BUCKET_REVIEW, None
    if len(anchor) < 2:
        return BUCKET_REVIEW, None

    hits = zones_containing(zone_boxes, anchor)
    if not hits:
        return BUCKET_NO_ZONE, None

    scored = [z for z in hits if z not in SAFE_ZONES]
    if scored:
        # Overlapping a safe zone does not excuse a row that also sits in a scored one.
        return BUCKET_REVIEW, scored[0]
    return BUCKET_SAFE, hits[0]


def cmd_worksheet(args: argparse.Namespace) -> int:
    """Emit a neutral annotation aid plus an empty label draft.

    The inventory below is a naive set difference over the engine's *normalisation* of
    each text entity. Using the engine's normaliser is required by the annotation
    guideline — labels and inference must share one definition of "the same text". Using
    the engine's *differ* is not: that would anchor the annotator to what the engine
    already finds, and the misses are the point.
    """
    from services.backend.infrastructure.audit.comparison.spatial_differ import SpatialDiffer

    corpus = _load_for_management(
        include_held_out=args.include_held_out,
        held_out_reason=args.reason,
    )
    pair = corpus.by_id(args.pair_id)
    if pair is None:
        raise SystemExit(
            f"No pair {args.pair_id!r} in the loaded corpus. Held-out pairs need "
            f"--include-held-out with a --reason."
        )

    ref_drawing, rev_drawing, ref_entities, rev_entities = pair.load()

    # The address the annotator copies into a label. A DXF handle when one exists;
    # otherwise the entity's line number in the frozen payload, because block-exploded
    # entities carry no handle at all and on the reference sheets that is nearly all of
    # them. See ExpectedFinding's docstring for the measurement.
    def address(side: str, index: int, entity: EvalEntity) -> str:
        return f"{side}-{entity.handle}" if entity.handle else f"{side}#{index}"

    def inventory(
        entities: list[EvalEntity], side: str
    ) -> dict[str, list[tuple[str, EvalEntity]]]:
        buckets: dict[str, list[tuple[str, EvalEntity]]] = {}
        for index, entity in enumerate(entities):
            display, key = SpatialDiffer._comparison_value(entity)
            if not display or not key:
                continue
            buckets.setdefault(key, []).append((address(side, index, entity), entity))
        return buckets

    ref_index = inventory(ref_entities, "REF")
    rev_index = inventory(rev_entities, "REV")
    ref_only = sorted(set(ref_index) - set(rev_index))
    rev_only = sorted(set(rev_index) - set(ref_index))
    shared = set(ref_index) & set(rev_index)
    multiplicity = [
        key for key in sorted(shared) if len(ref_index[key]) != len(rev_index[key])
    ]

    def layer_counts(entities: list[EvalEntity]) -> Counter[str]:
        return Counter(f"{e.layer}::{e.entity_type}" for e in entities)

    ref_layers, rev_layers = layer_counts(ref_entities), layer_counts(rev_entities)
    layer_delta = sorted(
        (
            (key, ref_layers.get(key, 0), rev_layers.get(key, 0))
            for key in set(ref_layers) | set(rev_layers)
            if ref_layers.get(key, 0) != rev_layers.get(key, 0)
        ),
        key=lambda row: abs(row[2] - row[1]),
        reverse=True,
    )

    # --- zone attribution -------------------------------------------------------------
    #
    # Which zone each row falls in, from the pair's **hand-aligned template** in the committed
    # manifest — the same boxes the user drew and the runner scores against, resolved through the
    # production `overrides_from_template_zones` so the Y-flip is exercised rather than
    # reimplemented. That flip is the one conversion whose failure mode is a plausible-looking
    # mirrored zone, and a mirrored zone here would tell the annotator to skip real findings.
    #
    # This is corpus data, not engine inference, so it does not violate the rule in this
    # function's docstring: the annotator's own rulebook is being applied, not the engine's
    # differ. Nothing is removed from the worksheet on the strength of it — rows are only
    # grouped, and every group is printed.
    from services.backend.infrastructure.audit.bom.zone_template_resolver import (
        overrides_from_template_zones,
    )

    # The reserved `_zone_polygons` key is carried through rather than stripped. Dropping it
    # flattened every reshaped zone to its bounding box here, so an L-shaped `notes` — the shape
    # used to reach content in a column gap without swallowing the neighbouring zone — read as a
    # full rectangle on the worksheet while the runner scored the L. `zones_containing` skips the
    # key and consults it. See `Gotcha - A Zone Template Gap Hid Half of a Real Change`.
    zone_boxes = {}
    for side, drawing, side_meta in (
        ("REF", ref_drawing, pair.ref),
        ("REV", rev_drawing, pair.rev),
    ):
        zone_boxes[side] = overrides_from_template_zones(
            side_meta.zone_template, (drawing.metadata or {}).get("render_bounds")
        )

    def zone_of(side: str, entity: EvalEntity) -> str | None:
        return zone_containing(zone_boxes.get(side, {}), anchor_of(entity))

    def triage(side: str, entity: EvalEntity) -> tuple[str, str | None]:
        return triage_row(zone_boxes.get(side, {}), anchor_of(entity))

    def describe(side: str, row: tuple[str, EvalEntity]) -> str:
        addr, entity = row
        display, _ = SpatialDiffer._comparison_value(entity)
        anchor = entity.geometry.get("insert") or entity.geometry.get("location") or []
        where = f"@({anchor[0]:.1f}, {anchor[1]:.1f})" if len(anchor) >= 2 else "@?"
        zone = zone_of(side, entity) or "—"
        return (
            f"| `{addr}` | {entity.entity_type} | {entity.layer} | {zone} | {where} | {display} |"
        )

    def bucketed(keys: list[str], index: dict, side: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {BUCKET_REVIEW: [], BUCKET_SAFE: [], BUCKET_NO_ZONE: []}
        for key in keys:
            for row in index[key]:
                out[triage(side, row[1])[0]].append(describe(side, row))
        return out

    handle_backed = sum(
        1 for e in ref_entities + rev_entities if e.handle and e.entity_type != "layer"
    )
    total_addressable = sum(1 for e in ref_entities + rev_entities if e.entity_type != "layer")

    lines: list[str] = [
        f"# Annotation worksheet — {pair.pair_id}",
        "",
        "> Generated by `tools/eval_corpus.py worksheet`. **Not** engine output — this is a",
        "> naive text-set difference, deliberately high-recall, so that a change the engine",
        "> misses is still in front of you. Read it next to the two drawings; it is an aid,",
        "> not a substitute for looking.",
        "",
        f"- reference: `{ref_drawing.file_name}` ({len(ref_entities)} entities)",
        f"- revision:  `{rev_drawing.file_name}` ({len(rev_entities)} entities)",
        f"- guideline: {GUIDELINE_VERSION}",
        "",
        "Rules that decide what is **not** a finding — safe zones (tolerance, シム表), sheet",
        "frame and grid labels, pure relocation with identical text, `%%c`/`%%d`/`%%p`",
        "transcodings, `22.7` vs `22.70` — are in",
        "`docs/vault/01 - Architecture/Eval Corpus Annotation Guideline.md`. Read it first.",
        "",
        "**Copy the `address` column verbatim into a label's `entity_handle`.** A value like",
        "`REV-1B2A` is a DXF handle; `REF#412` is line 412 of the frozen entity payload,",
        "used where no handle exists. Entities exploded out of a block never carry one, so",
        f"on this pair only {handle_backed} of {total_addressable} entities are",
        "handle-addressable — both forms are valid and the scorer resolves either.",
    ]

    ref_buckets = bucketed(ref_only, ref_index, "REF")
    rev_buckets = bucketed(rev_only, rev_index, "REV")
    header = [
        "| address | type | layer | zone | position | text |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    n_review = len(ref_buckets["review"]) + len(rev_buckets["review"])
    n_safe = len(ref_buckets["safe-zone"]) + len(rev_buckets["safe-zone"])
    n_nozone = len(ref_buckets["no-zone"]) + len(rev_buckets["no-zone"])
    n_all = n_review + n_safe + n_nozone

    if n_safe or n_nozone:
        lines += [
            "",
            "## How this worksheet is ordered",
            "",
            f"**{n_review} of {n_all} rows need your judgement.** The rest are grouped below "
            "under the guideline rule that covers them, because two flat lists of every "
            "unmatched string is mostly a list of things that can never be findings.",
            "",
            f"- **{n_review}** to review — the two sections immediately following.",
            f"- **{n_safe}** in a safe zone ({', '.join(sorted(SAFE_ZONES))}) — *\"Safe zones are "
            "never compared… a difference inside one is not a finding.\"*",
            f"- **{n_nozone}** in no zone at all — *\"Anything outside the `views` box that "
            "belongs to no zone\"* is out of scope, **and a real change sitting there is a "
            "zone-detection bug to file, not a label.**",
            "",
            "> [!IMPORTANT] Grouped, never hidden. Every row is still printed below.",
            "> The zones come from this pair's **hand-aligned template** in the committed "
            "manifest — the boxes you drew, which the runner also scores against — not from "
            "zone detection and not from the comparison engine. If a grouping looks wrong, the "
            "template is wrong, and that is worth knowing before you label 507 rows against it.",
        ]

    lines += [
        "",
        f"## Reference-only text — to review ({len(ref_buckets['review'])})",
        "",
        *header,
        *ref_buckets["review"],
        "",
        f"## Revision-only text — to review ({len(rev_buckets['review'])})",
        "",
        *header,
        *rev_buckets["review"],
    ]

    if n_safe:
        lines += [
            "",
            f"## Safe-zone rows — not findings ({n_safe})",
            "",
            "Reference data that does not change between revisions. Listed so you can confirm "
            "the grouping, not so you can label them. If something here *is* a real change, the "
            "safe-zone rule or the template box is wrong — say so in the draft's `notes`.",
            "",
            *header,
            *ref_buckets["safe-zone"],
            *rev_buckets["safe-zone"],
        ]

    if n_nozone:
        lines += [
            "",
            f"## Rows in no zone — out of scope ({n_nozone})",
            "",
            "Out of scope by the guideline. **If you believe a real change sits here, record it "
            "in `notes` and file a zone-detection bug — do not label it as a comparison "
            "finding.** This section is the one most worth skimming: it is where a mis-drawn "
            "template hides a genuine miss.",
            "",
            *header,
            *ref_buckets["no-zone"],
            *rev_buckets["no-zone"],
        ]

    lines += [
        "",
        f"## Same text, different count ({len(multiplicity)})",
        "",
        "Duplicated or de-duplicated content — often a repeated callout added or removed.",
        "",
        "| text | ref count | rev count |",
        "| :--- | ---: | ---: |",
    ]
    for key in multiplicity:
        display = SpatialDiffer._comparison_value(ref_index[key][0][1])[0]
        lines.append(f"| {display} | {len(ref_index[key])} | {len(rev_index[key])} |")
    lines += [
        "",
        f"## Entity-count delta by layer and type ({len(layer_delta)})",
        "",
        "Catches what a text diff cannot — geometry added, removed, or moved between",
        "layers. A view added or deleted shows up here even when it carries no new text.",
        "",
        "| layer::type | ref | rev | Δ |",
        "| :--- | ---: | ---: | ---: |",
    ]
    for key, ref_count, rev_count in layer_delta:
        lines.append(f"| {key} | {ref_count} | {rev_count} | {rev_count - ref_count:+d} |")
    lines.append("")

    out_dir = default_payload_dir().parent / "worksheets"
    worksheet_path = out_dir / f"{pair.pair_id}.md"
    write_text_stable(worksheet_path, "\n".join(lines))

    draft = {
        "pair_id": pair.pair_id,
        "guideline_version": GUIDELINE_VERSION,
        "annotator": "",
        "annotated_at": "",
        "notes": "",
        "findings": [],
        "not_findings": [],
    }
    draft_path = out_dir / f"{pair.pair_id}.labels.draft.json"
    if draft_path.exists() and not args.force:
        print(f"  draft already exists, left alone: {draft_path}")
    else:
        write_text_stable(draft_path, json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
        print(f"  draft:     {draft_path}")
    print(f"  worksheet: {worksheet_path}")
    print(
        f"  {len(ref_only)} ref-only, {len(rev_only)} rev-only, {len(multiplicity)} count "
        f"deltas, {len(layer_delta)} layer/type deltas"
    )
    if n_all:
        pct = (n_all - n_review) * 100 // n_all
        print(
            f"  {n_review} of {n_all} unmatched rows need judgement "
            f"({pct}% grouped as guideline-excluded: {n_safe} safe-zone, {n_nozone} no-zone)"
        )
    print("\nFill the draft in, then: tools/eval_corpus.py label --pair-id "
          f"{pair.pair_id} --from {draft_path}")
    return 0


def cmd_label(args: argparse.Namespace) -> int:
    """Validate a filled-in draft and install it as this pair's committed labels."""
    source = Path(args.source).resolve()
    if not source.exists():
        raise SystemExit(f"{source} does not exist.")
    raw = json.loads(read_text_stable(source))
    raw.setdefault("pair_id", args.pair_id)
    if not raw.get("annotated_at"):
        raw["annotated_at"] = datetime.now(UTC).date().isoformat()
    if not str(raw.get("annotator") or "").strip():
        raise SystemExit(
            "`annotator` is required. Ground truth is attributable work - a corpus with "
            "anonymous labels cannot be re-adjudicated when two pairs disagree."
        )

    labels = PairLabels.from_dict(raw)  # raises on schema or guideline-version drift
    if not labels.findings:
        print(
            "  [warn] zero findings. That is legitimate only for a null_mutation pair; for a "
            "human pair it usually means the draft was installed before it was filled in."
        )

    manifest = read_manifest()
    entry = next(
        (p for p in manifest.get("pairs") or [] if p.get("pair_id") == args.pair_id), None
    )
    if entry is None:
        raise SystemExit(f"No pair {args.pair_id!r} in the manifest — export it first.")

    rel = f"labels/{args.pair_id}.json"
    write_text_stable(
        default_fixtures_dir() / rel,
        json.dumps(labels.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    entry["labels"] = rel
    entry["label_state"] = "labelled"
    entry["category_counts"] = labels.category_counts
    entry["finding_count"] = len(labels.findings)
    entry["bulk_count"] = labels.bulk_count
    write_manifest(manifest)

    print(f"[ok] {args.pair_id}: {len(labels.findings)} finding(s) by {labels.annotator}")
    for category, count in labels.category_counts.items():
        if count:
            print(f"    {category}: {count}")
    if labels.bulk_count:
        print(
            f"    {labels.bulk_count} bulk finding(s) - the guideline requires these be "
            f"reported separately, since recall on them is easier than it looks."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval_corpus", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create an empty manifest")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    def add_pair_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--pair-id", required=True)
        p.add_argument("--ref", required=True)
        p.add_argument("--rev", required=True)
        p.add_argument("--provenance", default="human", choices=["human", "mutation"])
        p.add_argument(
            "--held-out",
            action="store_true",
            help="permanently held out; touched exactly once, at the end of Stage 0.5",
        )
        p.add_argument("--notes", default="")

    p_export = sub.add_parser("export", help="export a pair from the local Mongo")
    add_pair_args(p_export)
    p_export.add_argument("--mongo-uri", default=MONGO_URI_DEFAULT)
    p_export.add_argument("--mongo-db", default=MONGO_DB_DEFAULT)
    p_export.set_defaults(func=cmd_export)

    p_dxf = sub.add_parser("export-dxf", help="export a pair from two DXF files")
    add_pair_args(p_dxf)
    p_dxf.add_argument(
        "--render",
        action="store_true",
        help="run the background renderer to populate render_bounds (needs matplotlib)",
    )
    p_dxf.set_defaults(func=cmd_export_dxf)

    p_mut = sub.add_parser("mutate", help="generate mutation pairs from a registered base pair")
    p_mut.add_argument("--base", required=True, help="pair_id of the base pair")
    p_mut.add_argument("--side", default="rev", choices=["ref", "rev"])
    p_mut.add_argument("--count", type=int, default=10)
    p_mut.add_argument("--seed", type=int, default=1000)
    p_mut.add_argument("--edits", type=int, default=3, help="edits per non-null pair")
    p_mut.add_argument(
        "--operators",
        default="",
        help="comma-separated operator names to force, instead of a weighted random draw",
    )
    p_mut.add_argument(
        "--tag",
        default="mut",
        help="pair-id segment, so isolated probes (null/restyle/move) sit in their own "
        "id space instead of overwriting the random batch",
    )
    p_mut.add_argument("--verbose", action="store_true")
    p_mut.set_defaults(func=cmd_mutate)

    p_verify = sub.add_parser("verify", help="check payload digests and offline readiness")
    p_verify.set_defaults(func=cmd_verify)

    p_zones = sub.add_parser(
        "capture-zones",
        help="freeze each side's hand-aligned zone template into the manifest",
    )
    p_zones.add_argument("--pair-id", default="", help="one pair; default is every pair")
    p_zones.add_argument("--mongo-uri", default=MONGO_URI_DEFAULT)
    p_zones.add_argument("--mongo-db", default=MONGO_DB_DEFAULT)
    p_zones.add_argument(
        "--force",
        action="store_true",
        help="re-capture sides that already carry a template (moves the baseline)",
    )
    p_zones.set_defaults(func=cmd_capture_zones)

    p_status = sub.add_parser("status", help="progress against Stage 0b's exit criteria")
    p_status.set_defaults(func=cmd_status)

    p_ws = sub.add_parser("worksheet", help="emit an annotation worksheet and label draft")
    p_ws.add_argument("--pair-id", required=True)
    p_ws.add_argument("--include-held-out", action="store_true")
    p_ws.add_argument("--reason", default="")
    p_ws.add_argument("--force", action="store_true", help="overwrite an existing draft")
    p_ws.set_defaults(func=cmd_worksheet)

    p_bridge = sub.add_parser(
        "from-manual-check",
        help="convert an app Manual Check session into a label draft",
    )
    p_bridge.add_argument("--pair-id", required=True)
    p_bridge.add_argument(
        "--session-id", default="", help="omit to list the sessions covering this pair"
    )
    p_bridge.add_argument(
        "--mongo-uri",
        default="",
        help="default: the app's configured MONGO_URI (manual-check data is not synced local)",
    )
    p_bridge.add_argument("--mongo-db", default=MONGO_DB_DEFAULT)
    p_bridge.add_argument("--annotator", default="", help="override the session's annotator")
    p_bridge.add_argument("--out", default="", help="draft path (default: worksheets dir)")
    p_bridge.add_argument("--include-held-out", action="store_true")
    p_bridge.add_argument("--reason", default="")
    p_bridge.add_argument("--force", action="store_true", help="overwrite an existing draft")
    p_bridge.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="write the draft even though some markings did not convert",
    )
    p_bridge.set_defaults(func=cmd_from_manual_check)

    p_validate = sub.add_parser(
        "validate", help="check a draft in place without installing it"
    )
    p_validate.add_argument("--pair-id", required=True)
    p_validate.add_argument("--from", dest="source", required=True)
    p_validate.set_defaults(func=cmd_validate)

    p_label = sub.add_parser("label", help="install a filled-in label draft")
    p_label.add_argument("--pair-id", required=True)
    p_label.add_argument("--from", dest="source", required=True)
    p_label.set_defaults(func=cmd_label)

    return parser


def main(argv: list[str] | None = None) -> int:
    # This is a Japanese CAD domain and the default Windows console here is cp932, which
    # cannot encode a drawing whose file name carries CJK — or, less obviously, an em dash.
    # Without this a print statement kills the command after the payload has already been
    # written, which reads as a failed export when the export in fact succeeded.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover - non-tty stream
            pass

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
