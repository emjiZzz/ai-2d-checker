"""Stage 1a — a learned dismissal acts only in the category a human dismissed it in.

`get_learned_dismissals()` returns bare strings, and the orchestrator used to flatten every
category into one set and apply it to the drawing_views pool. Two silent consequences:

* a `title_block` dismissal suppressed drawing geometry, and
* a `drawing_views` dismissal never reached the notes or isometric pools, so the
  active-learning flywheel closed for exactly one of the three generic zones.

Suppression is the one direction this system cannot detect being wrong — nothing measures its
false-negative rate — so applying a dismissal outside its evidence is not a small liberty.

Measured effect on the corpus: zero. The live vault holds two patterns, `8`
(`drawing_views`) and `ユニットNo.` (`title_block`), and the eval scores byte-identical before
and after this change: P 0.98 / R 0.87 / F1 0.92. That is recorded rather than hidden — the
change is justified by the hazard it closes and by these tests, not by a metric move. The same
"nothing to measure" limit that blocks the Stage 0.5 sweep applies here, for the same reason:
there is not enough real data yet.

Note `8` is a single digit applied sheet-wide, which is the same defect class as the structured
BOM value `1` in [[Gotcha - A Short Structured Value Suppresses Its Own Zone]].
"""

import pytest

from services.backend.infrastructure.knowledge.vault_sync import (
    LOOSE_MATCH_MIN_LENGTH,
    LearnedDismissal,
    VaultSyncManager,
)

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

## Learned Rule — Pattern: `8`
- **Client**: General
- **Category**: `drawing_views`
- **Human Dismissals**: 4 confirmed overrides
- **Directive**: Treat pattern `8` as static legend/template callout.
"""


def _make_vault(tmp_path):
    rules_dir = tmp_path / RULES_DIR
    rules_dir.mkdir(parents=True)
    (rules_dir / "Learned_Rules_General.md").write_text(LEARNED_NOTE, encoding="utf-8")
    return VaultSyncManager(vault_path=tmp_path)


# ---------------------------------------------------------------------------
# The scope itself
# ---------------------------------------------------------------------------

def test_a_rule_carries_the_category_it_was_learned_in(tmp_path):
    mgr = _make_vault(tmp_path)

    rules = mgr.get_learned_dismissal_rules()

    assert {(r.pattern, r.category) for r in rules} == {
        ("ユニットNo.", "title_block"),
        ("8", "drawing_views"),
    }


def test_requesting_one_category_returns_only_that_category(tmp_path):
    """The property the orchestrator depends on: a drawing_views pool asking for its own
    patterns must not receive title_block's."""
    mgr = _make_vault(tmp_path)

    views = mgr.get_learned_dismissal_rules(category="drawing_views")

    assert [r.pattern for r in views] == ["8"]
    assert all(r.category == "drawing_views" for r in views)


def test_a_category_with_no_learned_rules_gets_nothing(tmp_path):
    """Not a fallback to the global set — the notes pool having no learned evidence means it
    suppresses nothing, which is the safe direction."""
    mgr = _make_vault(tmp_path)

    assert mgr.get_learned_dismissal_rules(category="notes_section") == []
    assert mgr.get_learned_dismissal_rules(category="bill_of_materials") == []


# ---------------------------------------------------------------------------
# Match modes
# ---------------------------------------------------------------------------

def test_a_short_pattern_stays_exact(tmp_path):
    """`8` is one character. It must never be widened — a prefix or substring match on a single
    digit would suppress every dimension beginning with 8."""
    mgr = _make_vault(tmp_path)

    rule = mgr.get_learned_dismissal_rules(category="drawing_views")[0]

    assert len(rule.pattern) < LOOSE_MATCH_MIN_LENGTH
    assert rule.match_mode == "exact"
    assert rule.matches("8")
    assert not rule.matches("8.5")
    assert not rule.matches("18")
    assert not rule.matches("80")


def test_a_long_pattern_is_normalized(tmp_path):
    mgr = _make_vault(tmp_path)

    rule = mgr.get_learned_dismissal_rules(category="title_block")[0]

    assert rule.match_mode == "normalized"


def test_matching_folds_width_and_case():
    """A pattern and the entity text it is compared against must be folded by ONE definition.
    Full-width is how this client's CAD standard draws its labels, so a rule authored from a
    half-width dismissal has to catch the full-width glyph and vice versa."""
    rule = LearnedDismissal(pattern="ABC", category="drawing_views", match_mode="normalized")

    assert rule.matches("abc")
    assert rule.matches("ＡＢＣ")
    assert rule.matches("  ABC  ")
    assert not rule.matches("ABCD")


def test_prefix_mode_is_available_but_not_the_default():
    """Prefix exists for a future pattern that needs it. Nothing emits it today, deliberately:
    it is the mode most able to over-suppress, so it should be opted into with evidence."""
    rule = LearnedDismissal(pattern="NOTE", category="notes_section", match_mode="prefix")

    assert rule.matches("NOTE 1")
    assert rule.matches("note 12")
    assert not rule.matches("SEE NOTE 1")


def test_an_empty_pattern_matches_nothing():
    """A blank rule would empty the pool it is applied to."""
    rule = LearnedDismissal(pattern="", category="drawing_views", match_mode="exact")

    assert not rule.matches("anything")
    assert not rule.matches("")


# ---------------------------------------------------------------------------
# Back-compat
# ---------------------------------------------------------------------------

def test_the_string_api_is_unchanged(tmp_path):
    """`get_learned_dismissals` keeps its shape. It is not deprecated, it is narrower — several
    tests and the vault's own parse output depend on the flat form."""
    mgr = _make_vault(tmp_path)

    assert sorted(mgr.get_learned_dismissals()) == ["8", "ユニットNo."]
    assert mgr.get_learned_dismissals("title_block") == ["ユニットNo."]


def test_flat_vault_patterns_need_no_migration(tmp_path):
    """The vault stores prose, not a schema. Every existing note parses into a structured rule
    with a mode derived from its length — so there is nothing on disk to migrate, which is the
    same posture as the permanent `rag` input alias."""
    mgr = _make_vault(tmp_path)

    rules = mgr.get_learned_dismissal_rules()

    assert len(rules) == 2
    assert all(r.match_mode in {"exact", "normalized"} for r in rules)
    assert all(r.pattern for r in rules)
