"""Tests for Pillar 1 (vault -> runtime rule sync).

Two defects, both measured on the real vault on 2026-07-29:

1. It walked the ENTIRE vault and concatenated every note, so architecture notes, gotchas
   and ADRs — documentation *about* the system — steered `safe_filter`. Writing a gotcha that
   quoted a Japanese anchor changed what the comparison engine excluded.

2. The inline-code regex ignored triple-backtick fences. Across a concatenated blob it
   paired the closing backtick of one fence with the opening backtick of the next and captured
   everything between. Result: 36 of 54 "tolerance keywords" were multi-hundred-character
   markdown spans containing whole mermaid diagrams. None could substring-match a CAD string,
   so Pillar 1 contributed nothing at all while appearing to work.

Also covered: the Pillar 3 -> Pillar 1 loop, which never closed. `AutoDocEngine` wrote learned
dismissal rules into the vault and nothing read them back.
"""
import pytest

from services.backend.infrastructure.knowledge.vault_sync import VaultSyncManager

RULES_DIR = "08 - Client Domain & CAD Rules"

LEARNED_NOTE = """---
title: Learned Rules - General
type: domain-rules
---

# Learned Rules — Client: General

## Learned Rule — Pattern: `ユニットNo.`
- **Client**: General
- **Category**: `title_block`
- **Human Dismissals**: 3 confirmed overrides
- **Directive**: Treat pattern `ユニットNo.` as static legend/template callout.

## Learned Rule — Pattern: `12.5S`
- **Client**: General
- **Category**: `drawing_views`
- **Human Dismissals**: 4 confirmed overrides
- **Directive**: Treat pattern `12.5S` as static legend/template callout.
"""

# A note of the kind that used to poison the keyword set: a fenced diagram whose content
# mentions tolerance, sitting next to inline code spans.
FENCED_NOTE = """---
title: Domain Standards
---

Some prose about `指示外公差` tables.

```mermaid
graph TD
    A["general tolerance table"] --> B["公差の区分"]
```

More prose mentioning `仕上精度` here.
"""


def _make_vault(tmp_path, rules: dict, other: dict | None = None):
    rules_dir = tmp_path / RULES_DIR
    rules_dir.mkdir(parents=True)
    for name, body in rules.items():
        (rules_dir / name).write_text(body, encoding="utf-8")
    for folder, files in (other or {}).items():
        d = tmp_path / folder
        d.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (d / name).write_text(body, encoding="utf-8")
    return VaultSyncManager(vault_path=tmp_path)


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

def test_notes_outside_the_client_rules_folder_do_not_steer_runtime(tmp_path):
    """The regression: documentation was a runtime input."""
    gotcha = "A gotcha note discussing `machining tolerance` and `表面粗さの区分` at length."
    mgr = _make_vault(
        tmp_path,
        rules={"Standards.md": "Prose with `指示外公差`."},
        other={"06 - Gotchas & Debugging Lessons": {"Gotcha - Something.md": gotcha}},
    )

    keywords = mgr.get_tolerance_keywords()

    assert "machining tolerance" not in keywords
    assert not any("粗さの区分" in k and "表面" in k for k in keywords if len(k) > 8), (
        "a gotcha note contributed a runtime keyword"
    )


def test_missing_client_rules_folder_falls_back_to_defaults(tmp_path):
    mgr = VaultSyncManager(vault_path=tmp_path / "nonexistent")

    keywords = mgr.get_tolerance_keywords()

    # The built-in defaults still apply; the engine must not lose tolerance filtering.
    assert "指示外公差" in keywords
    assert mgr.get_learned_dismissals() == []


# ---------------------------------------------------------------------------
# Fence handling
# ---------------------------------------------------------------------------

def test_fenced_code_blocks_do_not_leak_giant_spans(tmp_path):
    """The mechanism behind 36 junk keywords."""
    mgr = _make_vault(tmp_path, rules={"Standards.md": FENCED_NOTE})

    keywords = mgr.get_tolerance_keywords()

    assert not any("mermaid" in k for k in keywords)
    assert not any("graph" in k for k in keywords)
    assert not any("\n" in k for k in keywords), "a captured span crossed lines"


def test_no_keyword_is_a_prose_blob(tmp_path):
    """Guard the length bound directly — a keyword is a phrase, not a paragraph."""
    mgr = _make_vault(tmp_path, rules={"Standards.md": FENCED_NOTE, "Learned.md": LEARNED_NOTE})

    for keyword in mgr.get_tolerance_keywords():
        assert len(keyword) <= 60, f"blob captured as keyword: {keyword[:80]!r}"


def test_real_inline_anchors_are_still_extracted(tmp_path):
    """Fence-stripping must not cost legitimate domain vocabulary."""
    note = "The table is headed `指示外公差` and sometimes `機械加工公差`."
    mgr = _make_vault(tmp_path, rules={"Standards.md": note})

    keywords = mgr.get_tolerance_keywords()

    assert "機械加工公差" in keywords


# ---------------------------------------------------------------------------
# Pillar 3 -> Pillar 1: the flywheel
# ---------------------------------------------------------------------------

def test_learned_rules_are_read_back(tmp_path):
    """AutoDocEngine wrote these notes and nothing ever read them."""
    mgr = _make_vault(tmp_path, rules={"Learned_Rules_General.md": LEARNED_NOTE})

    assert sorted(mgr.get_learned_dismissals()) == ["12.5S", "ユニットNo."]


def test_learned_rules_are_category_scoped(tmp_path):
    mgr = _make_vault(tmp_path, rules={"Learned_Rules_General.md": LEARNED_NOTE})

    assert mgr.get_learned_dismissals("title_block") == ["ユニットNo."]
    assert mgr.get_learned_dismissals("drawing_views") == ["12.5S"]
    assert mgr.get_learned_dismissals("bill_of_materials") == []


def test_a_rule_block_does_not_capture_the_next_blocks_category(tmp_path):
    """The two blocks are adjacent; a greedy match would give both the same category."""
    mgr = _make_vault(tmp_path, rules={"Learned_Rules_General.md": LEARNED_NOTE})

    assert "12.5S" not in mgr.get_learned_dismissals("title_block")


def test_duplicate_patterns_are_not_repeated(tmp_path):
    doubled = LEARNED_NOTE + LEARNED_NOTE
    mgr = _make_vault(tmp_path, rules={"Learned_Rules_General.md": doubled})

    assert mgr.get_learned_dismissals("title_block").count("ユニットNo.") == 1


def test_prose_mentioning_learned_rules_is_not_parsed_as_one(tmp_path):
    """A note *describing* the format must not inject rules."""
    prose = "The engine writes blocks headed 'Learned Rule — Pattern' with a Category field."
    mgr = _make_vault(tmp_path, rules={"Notes.md": prose})

    assert mgr.get_learned_dismissals() == []


def test_reload_picks_up_a_newly_written_rule(tmp_path):
    """AutoDocEngine writes a note then triggers a reload; that path must work."""
    mgr = _make_vault(tmp_path, rules={"Standards.md": "Prose."})
    assert mgr.get_learned_dismissals() == []

    (tmp_path / RULES_DIR / "Learned_Rules_General.md").write_text(LEARNED_NOTE, encoding="utf-8")
    mgr.load_live_rules(force_reload=True)

    assert "ユニットNo." in mgr.get_learned_dismissals()
