"""
Guards `docs/vault/00 - AI Maturity Status.md` — the ledger that records which rung of the AI
maturity ladder this system is actually on.

Why this test exists: documentation that can drift silently is how this project acquired a phantom.
`CLAUDE.md` advertised "the four V2 gaps" for months, and the gap analysis eventually had to record
that the phrase "has no source in this vault — no such list was ever written down." The ledger makes
a *claim* about system state, so the claim is checked against the filesystem here.

The central rule: a rung claim must be backed by evidence that exists. Rung >= 1 asserts real
retrieval, so the fake embedding model must be gone and `infrastructure/retrieval/` must be present.
Rung >= 3 asserts a trainable pipeline, so the params object and learned matcher must exist. If an
agent bumps `current_rung` without doing the work, this fails.

Deliberately a lightweight text/frontmatter parse, not a Markdown parser — the ledger's structure is
a plain YAML frontmatter block plus fixed headings, and keeping this simple mirrors
`test_taxonomy_consistency.py`.

See CLAUDE.md constraint 5.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VAULT = REPO_ROOT / "docs" / "vault"
LEDGER_PATH = VAULT / "00 - AI Maturity Status.md"
BACKEND = REPO_ROOT / "services" / "backend"
COMPARISON = BACKEND / "infrastructure" / "audit" / "comparison"

# Rungs, as declared in the ledger's own frontmatter comment.
RUNG_NAMES = {
    0: "pre-RAG",
    1: "Basic RAG",
    2: "Fine-Tuned RAG",
    3: "End-to-End Trainable",
    4: "Agentic & Adaptive",
}

# Headings the ledger must keep, because CLAUDE.md constraint 5 tells agents to update them by name.
REQUIRED_SECTIONS = (
    "Current rung",
    "What's next",
    "Stage board",
    "Work log",
    "Negative results",
)

# Every stage named in `AI Maturity Ladder — Staged Plan`. A stage board that has quietly dropped
# one is a board that no longer describes the plan.
REQUIRED_STAGES = ("Stage 0", "Stage 0.5", "Stage 1", "Stage 2", "Stage 3", "Stage 4")


def _read_ledger() -> str:
    assert LEDGER_PATH.exists(), (
        f"The AI maturity ledger is missing: {LEDGER_PATH}\n"
        "It is the canonical record of which rung the system is on (CLAUDE.md constraint 5). "
        "If the vault moved, update this test rather than deleting the ledger."
    )
    return LEDGER_PATH.read_text(encoding="utf-8")


def _frontmatter(source: str) -> dict[str, str]:
    """Parses the leading `---` YAML block. Flat string values only, which is all the ledger uses."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", source, re.DOTALL)
    assert match, "Ledger must open with a YAML frontmatter block delimited by ---"

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        # Strip trailing `# comment` and surrounding quotes.
        value = re.sub(r"\s+#.*$", "", value).strip().strip("\"'")
        fields[key.strip()] = value
    return fields


@pytest.fixture(scope="module")
def ledger() -> str:
    return _read_ledger()


@pytest.fixture(scope="module")
def meta(ledger: str) -> dict[str, str]:
    return _frontmatter(ledger)


def test_ledger_declares_a_valid_rung(meta: dict[str, str]) -> None:
    assert "current_rung" in meta, "Ledger frontmatter must declare `current_rung`"
    rung = int(meta["current_rung"])
    assert rung in RUNG_NAMES, f"current_rung must be one of {sorted(RUNG_NAMES)}, got {rung}"


def test_ledger_declares_rung_evidence(meta: dict[str, str]) -> None:
    """A rung claim without evidence is the failure mode this whole file exists to prevent."""
    assert "rung_evidence" in meta, (
        "Ledger frontmatter must declare `rung_evidence`. Use the literal `none` at rung 0."
    )
    rung = int(meta["current_rung"])
    evidence = meta["rung_evidence"].strip().lower()

    if rung == 0:
        assert evidence == "none", (
            "At rung 0 there is no eval report yet, so `rung_evidence` must be the literal `none`."
        )
    else:
        assert evidence != "none", (
            f"current_rung is {rung} ({RUNG_NAMES[rung]}) but rung_evidence is `none`.\n"
            "Every rung above 0 is defined by a measurement. Link the eval report that justifies "
            "the claim, or drop the rung back to 0."
        )
        evidence_path = REPO_ROOT / meta["rung_evidence"].strip()
        assert evidence_path.exists(), (
            f"rung_evidence points at a file that does not exist: {evidence_path}\n"
            "A dead evidence link is the same defect as no evidence link."
        )


def test_ledger_has_the_sections_agents_are_told_to_update(ledger: str) -> None:
    missing = [s for s in REQUIRED_SECTIONS if s.lower() not in ledger.lower()]
    assert not missing, (
        f"Ledger is missing sections agents are directed to update: {missing}. "
        "See CLAUDE.md constraint 5."
    )


def test_stage_board_covers_every_planned_stage(ledger: str) -> None:
    missing = [s for s in REQUIRED_STAGES if s not in ledger]
    assert not missing, (
        f"Stage board does not mention: {missing}. Every stage in "
        "`AI Maturity Ladder — Staged Plan` must appear, so 'done' stays checkable."
    )


def test_rung_1_requires_real_retrieval(meta: dict[str, str]) -> None:
    """Rung 1 claims Basic RAG. The fake stack must be gone and a real one present."""
    if int(meta["current_rung"]) < 1:
        pytest.skip("Below rung 1; retrieval work not yet claimed.")

    fake_embeddings = BACKEND / "infrastructure" / "ai" / "embeddings" / "local_embedding_model.py"
    assert not fake_embeddings.exists(), (
        "current_rung >= 1 claims real retrieval, but the fake embedding model still exists at "
        f"{fake_embeddings}. It returns SHA-256-seeded Gaussian noise with hardcoded English "
        "keyword bumps — it is not an embedding, so the rung claim is false while it is wired in."
    )

    fake_store = BACKEND / "infrastructure" / "ai" / "vectorstore" / "lancedb_manager.py"
    assert not fake_store.exists(), (
        f"current_rung >= 1 but the fake vector store still exists at {fake_store} "
        "(it is a JSON file plus a numpy loop, not LanceDB)."
    )

    retrieval_pkg = BACKEND / "infrastructure" / "retrieval"
    assert retrieval_pkg.is_dir(), (
        f"current_rung >= 1 but there is no retrieval package at {retrieval_pkg}."
    )


def test_rung_3_requires_the_trainable_substrate(meta: dict[str, str]) -> None:
    """Rung 3 claims end-to-end trainable: calibrated params plus a learned matcher."""
    if int(meta["current_rung"]) < 3:
        pytest.skip("Below rung 3; learned-matcher work not yet claimed.")

    for name, why in (
        ("params.py", "Stage 0.5 extracts every tuning constant into ComparisonParams"),
        ("learned_matcher.py", "Stage 3 replaces the threshold cascade with a learned matcher"),
    ):
        path = COMPARISON / name
        assert path.exists(), f"current_rung >= 3 but {path} is missing — {why}."


def test_learned_model_is_not_stranded_in_the_gitignored_vault(meta: dict[str, str]) -> None:
    """A model that cannot be committed, diffed or shipped is not trainable infrastructure.

    `docs/vault/` is gitignored, so a bundle living only there exists on one machine. Stage 0h moves
    it to services/backend/storage/models/. Enforced from rung 3, where trainability is the claim.
    """
    if int(meta["current_rung"]) < 3:
        pytest.skip("Below rung 3; model relocation is a Stage 0h item, enforced from rung 3.")

    stranded = VAULT / "09 - Learned Models" / "finding_classifier.joblib"
    assert not stranded.exists(), (
        f"current_rung >= 3 but the model bundle is still in the gitignored vault at {stranded}. "
        "Move it to services/backend/storage/models/ (Stage 0h). Model Card.md stays in the vault."
    )
