"""
Guards the R0 exit criterion: no module claims an AI capability it does not have.

Why this test exists. The standards-audit pipeline shipped for months with an embedding module
that returned `np.random.default_rng(sha256(text))` — 384 dimensions of Gaussian noise seeded from
a hash — behind docstrings advertising SentenceTransformers and ONNX Runtime, feeding a "LanceDB"
store that was a numpy loop over a JSON file that never existed on disk.

The reason it survived is the reason this test is worth having: a fake that raises gets found,
and a fake that answers does not. Hash-seeded vectors are finite, normalized and deterministic,
so cosine similarity over them returns ranked, scored, entirely plausible results. Nothing
downstream — no caller, no test, no log line — could distinguish that from a real model. R0
deleted the stack rather than repairing it, and this test is what stops it growing back.

Deliberately AST-based rather than a text scan, for a specific reason discovered while writing it:
the tombstone comments left at each deletion site *quote the defect they replaced*, so a grep for
`default_rng(sha256(...))` matches the very comments explaining that it is gone. Comments are not
claims. An AST parse discards them and leaves only executable code plus docstrings, which is
exactly the distinction that matters here — a module's docstring is its claim about itself; a
comment recording why something was removed is history.

See `docs/vault/01 - Architecture/Standards Knowledge — Staged Plan.md` (Stage R0) and
`docs/vault/07 - Architecture Decision Records (ADRs)/ADR-008 The Second Brain — Retrieval-Only
Local Knowledge.md`.
"""
import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "services" / "backend"
AI_PACKAGE = BACKEND / "infrastructure" / "ai"

# `.venv` lives *inside* services/backend, so every walk here must exclude it — otherwise this
# test grades numpy's and matplotlib's test suites instead of ours.
EXCLUDED_DIRS = {".venv", "__pycache__", "storage", "node_modules", ".git"}

# Functions that produce a random stream. Seeding one of these from a hash is the defect.
RNG_FACTORIES = {"default_rng", "seed", "RandomState", "PCG64", "MT19937", "Generator"}
HASH_FUNCTIONS = {"sha256", "sha1", "sha512", "md5", "blake2b", "blake2s"}

# A docstring naming one of these is claiming the dependency. If the package is not importable,
# the claim is false. Maps the claim as it appears in prose -> the module that would back it.
CAPABILITY_CLAIMS = {
    "sentencetransformer": "sentence_transformers",
    "sentence-transformers": "sentence_transformers",
    "onnx": "onnxruntime",
    "lancedb": "lancedb",
    "faiss": "faiss",
    "huggingface": "transformers",
}

# Deleted by R0. Each entry is (path relative to services/backend, why it went).
DELETED_FAKES = [
    (
        "infrastructure/ai/embeddings/local_embedding_model.py",
        "returned SHA-256-seeded Gaussian noise with hardcoded English keyword bumps, behind a "
        "docstring claiming SentenceTransformers/ONNX; `_load_model` assigned the *string* "
        "'ONNX_Quantized_MiniLM'",
    ),
    (
        "infrastructure/ai/vectorstore/lancedb_manager.py",
        "was not LanceDB — an index_shards.json plus a numpy loop, over a file that never existed",
    ),
    (
        "infrastructure/ai/vectorstore/embedding_provider.py",
        "wrapped the fake embedding model; also the site of the embed_text/embed_texts defect",
    ),
    (
        "infrastructure/ai/vectorstore/retrieval_engine.py",
        "queried the fake store, so every 'no relevant lessons' result was unfalsifiable",
    ),
    (
        "infrastructure/ai/vectorstore/standards_indexer.py",
        "wrote hash-derived vectors on every standards upload",
    ),
    (
        "infrastructure/ai/vectorstore/vector_persistence.py",
        "sandboxed paths for a store that held nothing",
    ),
    (
        "infrastructure/ai/reasoning/drawing_similarity_engine.py",
        "calculate_drawing_distance returned a hardcoded 0.85 and find_systemic_drafting_errors "
        "fabricated a finding with an invented 0.88 frequency",
    ),
    (
        "infrastructure/ai/geometry/vector_geometry_index.py",
        "documented cosine similarity search and returned an empty list",
    ),
    (
        "infrastructure/ai/geometry/geometry_search_engine.py",
        "documented symbol clustering and returned an empty dict",
    ),
]


def _first_party_py_files() -> list[Path]:
    """Every .py file we actually wrote — backend and tools, never dependencies."""
    files: list[Path] = []
    for root in (BACKEND, REPO_ROOT / "tools"):
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if EXCLUDED_DIRS.isdisjoint(path.relative_to(REPO_ROOT).parts):
                files.append(path)
    return files


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _call_name(node: ast.Call) -> str:
    """`np.random.default_rng(...)` -> 'default_rng'; `sha256(...)` -> 'sha256'."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_no_random_stream_is_seeded_from_a_hash():
    """The exact defect that shipped: a hash of text used as an RNG seed to synthesise a vector.

    Hashing is fine. Seeded RNGs are fine — `infrastructure/eval/mutator.py` seeds one deliberately
    so that generated mutation labels are reproducible from a recipe rather than 54 committed
    files. What is never fine is routing a *hash* into the *seed*, because the output is a stable,
    plausible, meaningless vector.
    """
    offenders: list[str] = []

    for path in _first_party_py_files():
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in RNG_FACTORIES:
                continue
            # Does anything inside this call's arguments compute a hash?
            for arg in node.args + [kw.value for kw in node.keywords]:
                for inner in ast.walk(arg):
                    if isinstance(inner, ast.Call) and _call_name(inner) in HASH_FUNCTIONS:
                        rel = path.relative_to(REPO_ROOT)
                        offenders.append(
                            f"{rel}:{node.lineno} — {_call_name(inner)} feeds an RNG seed"
                        )

    assert not offenders, (
        "A random stream is being seeded from a hash:\n  "
        + "\n  ".join(offenders)
        + "\n\nThis is the defect R0 deleted. It produces deterministic, normalized, "
        "plausible-looking vectors that no downstream consumer can distinguish from a real "
        "embedding — cosine similarity over them returns ranked scored results and nothing "
        "reports an error. Use real retrieval (`infrastructure/retrieval/`, R1) instead. "
        "See ADR-008."
    )


def test_no_docstring_claims_an_uninstalled_dependency():
    """A module may not advertise a capability whose package is not installed.

    Docstrings only — comments are excluded on purpose. The R0 deletion sites carry comments that
    quote the old ONNX/LanceDB claims in order to explain what was removed; recording history is
    not the same as making a claim, and a test that cannot tell them apart would punish the
    documentation this project depends on.
    """
    installed = {
        module: importlib.util.find_spec(module) is not None
        for module in set(CAPABILITY_CLAIMS.values())
    }

    offenders: list[str] = []
    for path in _first_party_py_files():
        tree = _parse(path)
        if tree is None:
            continue

        nodes = [tree] + [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        for node in nodes:
            doc = ast.get_docstring(node)
            if not doc:
                continue
            lowered = doc.lower()
            for claim, module in CAPABILITY_CLAIMS.items():
                if claim in lowered and not installed[module]:
                    rel = path.relative_to(REPO_ROOT)
                    # `ast.Module` has no lineno — a module-level docstring is at line 1. This
                    # defaulted attribute is not defensive padding: without it the *failure*
                    # path raised AttributeError instead of reporting, so the first real
                    # module-docstring offender crashed the guard rather than naming itself.
                    line = getattr(node, "lineno", 1)
                    offenders.append(
                        f"{rel}:{line} — docstring says {claim!r}, "
                        f"but {module!r} is not installed"
                    )

    assert not offenders, (
        "A docstring claims a capability the environment cannot provide:\n  "
        + "\n  ".join(offenders)
        + "\n\n`local_embedding_model.py` did exactly this: its docstring promised "
        "'HuggingFace/SentenceTransformers' and 'ONNX Runtime' while `_load_model` assigned the "
        "string 'ONNX_Quantized_MiniLM' and the real work was np.random. Either install the "
        "dependency and use it, or describe what the code actually does."
    )


@pytest.mark.parametrize(
    "relative_path,reason",
    DELETED_FAKES,
    ids=[Path(p).stem for p, _ in DELETED_FAKES],
)
def test_deleted_fake_modules_stay_deleted(relative_path: str, reason: str):
    """R0 removed these. Re-adding one should be a red test, not a quiet regression.

    `test_maturity_ledger.py::test_rung_1_requires_real_retrieval` also asserts the first two are
    gone, but only once `current_rung >= 1`. This holds at rung 0, which is where the system is.
    """
    path = BACKEND / relative_path
    assert not path.exists(), (
        f"{relative_path} is back. It was deleted by R0 because it {reason}.\n\n"
        "If real functionality is needed here, build it in `infrastructure/retrieval/` (R1, "
        "lexical-first, zero new dependencies) rather than restoring this module. See "
        "docs/vault/01 - Architecture/Standards Knowledge — Staged Plan.md."
    )


def test_the_ai_package_contains_only_modules_that_survived_the_audit():
    """Pins the R0 verdict for the whole package, so a new fake cannot slip in beside the old ones.

    `graph_builder.py` and `explainability/` are kept deliberately: they have zero callers, but
    they are honest — a real in-memory graph and real pure functions. Dead code is a separate
    cleanup from fake code, and R0 was scoped to the second.
    """
    if not AI_PACKAGE.is_dir():
        pytest.skip("infrastructure/ai/ has been removed entirely.")

    surviving = {
        str(p.relative_to(AI_PACKAGE)).replace("\\", "/")
        for p in AI_PACKAGE.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    expected = {
        "copilot/prompt_guardrails.py",
        "copilot/streaming_engine.py",
        "explainability/confidence_interpreter.py",
        "explainability/remediation_engine.py",
        "explainability/standards_reference_mapper.py",
        "explainability/violation_reasoner.py",
        "knowledge_graph/graph_builder.py",
    }

    added = surviving - expected
    assert not added, (
        f"New modules appeared under infrastructure/ai/: {sorted(added)}. "
        "This package was audited module-by-module in R0 and every remaining file was confirmed to "
        "do what it says. Anything new here needs the same scrutiny — if it performs retrieval or "
        "embedding it almost certainly belongs in `infrastructure/retrieval/` instead. Update this "
        "list once the module has been reviewed."
    )
