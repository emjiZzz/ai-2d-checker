"""
Live Obsidian Vault-to-Runtime Sync Manager (Pillar 1).

Reads the client domain-rule notes in the Obsidian Second Brain vault at runtime, extracting
live tolerance keywords, surface roughness regexes and human-learned dismissal patterns to
inject into backend RAG filters.

## Scope: `08 - Client Domain & CAD Rules/` ONLY

This used to walk the ENTIRE vault and concatenate every note, which had two consequences:

* It did not work. The inline-code regex does not account for triple-backtick fences, so
  across a concatenated blob it matched the span *between* one fence and the next. Measured
  2026-07-29: 36 of 54 "tolerance keywords" were multi-hundred-character markdown spans
  containing whole mermaid diagrams and frontmatter. None could ever substring-match a CAD
  string, so Pillar 1 contributed nothing at all.
* Documentation was a runtime input. Writing a gotcha note that quoted a Japanese anchor
  changed what `safe_filter` excluded from comparison. Editing the vault to improve its prose
  measurably increased the junk in this rule set.

Domain rules belong in the domain-rules folder. Architecture notes, gotchas and ADRs are
documentation *about* the system and must not steer it.
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
try:
    from ...logger import logger
except Exception:
    try:
        from logger import logger
    except Exception:
        import logging
        logger = logging.getLogger("vault_sync")

# Patterns at or above this length may match after normalization; below it they must match the
# raw normalized text exactly. Same reasoning, and the same number, as
# `ComparisonParams.min_structured_value_length`: a short string carries no evidence that the
# entity it matches is the one a human dismissed. This vault currently holds a learned pattern
# that is the single digit `8`.
LOOSE_MATCH_MIN_LENGTH = 3

_EXACT = "exact"
_NORMALIZED = "normalized"
_PREFIX = "prefix"


@dataclass(frozen=True)
class LearnedDismissal:
    """One pattern a human dismissed >= 3 times, with the scope it is allowed to act in.

    Before this was structured, `get_learned_dismissals()` returned bare strings and the
    orchestrator flattened every category into one set applied to the drawing_views pool. Two
    consequences, both silent:

    * a pattern learned in `title_block` filtered `drawing_views` content, and
    * a pattern learned in `drawing_views` never reached the notes or isometric pools.

    `category` is the scope, not a label. A dismissal is evidence about one category; applying
    it elsewhere is an unaudited guess, and suppression is the one direction this system cannot
    detect being wrong -- nothing measures its false-negative rate.
    """

    pattern: str
    category: str
    match_mode: str = _EXACT

    @property
    def normalized_pattern(self) -> str:
        return _normalize_for_match(self.pattern)

    def matches(self, text: str) -> bool:
        """True when `text` should be suppressed by this rule."""
        candidate = _normalize_for_match(text)
        if not candidate or not self.normalized_pattern:
            return False
        if self.match_mode == _PREFIX:
            return candidate.startswith(self.normalized_pattern)
        # `exact` and `normalized` differ in how the pattern was AUTHORED, not in the
        # comparison: both compare whole strings. The distinction is kept because it records
        # whether the pattern was short enough to be collision-prone, which is what a future
        # reader needs in order to decide whether widening it is safe.
        return candidate == self.normalized_pattern


def _normalize_for_match(text: str) -> str:
    """NFKC + casefold + whitespace collapse. Mirrors `orchestrator._normalize_value_text` so a
    pattern and the entity text it is compared against are folded by one definition."""
    folded = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    return re.sub(r"\s+", " ", folded)


def _match_mode_for(pattern: str) -> str:
    """`normalized` at >= LOOSE_MATCH_MIN_LENGTH, `exact` below."""
    return _NORMALIZED if len(_normalize_for_match(pattern)) >= LOOSE_MATCH_MIN_LENGTH else _EXACT


class VaultSyncManager:
    """Manages parsing and caching of live rules from the Obsidian Second Brain vault."""

    _instance: Optional['VaultSyncManager'] = None
    _cached_rules: Optional[Dict[str, Any]] = None

    def __init__(self, vault_path: Optional[Path] = None):
        if vault_path:
            self.vault_path = vault_path
        else:
            # Resolve repo root: services/backend/infrastructure/knowledge/vault_sync.py -> 4 parents up -> repo root
            backend_dir = Path(__file__).resolve().parent.parent.parent
            repo_root = backend_dir.parent.parent
            self.vault_path = repo_root / "docs" / "vault"

    @classmethod
    def get_instance(cls) -> 'VaultSyncManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # The only folder that steers runtime behaviour. See the module docstring.
    CLIENT_RULES_DIR = "08 - Client Domain & CAD Rules"

    def _read_all_markdown_contents(self) -> str:
        """Reads and concatenates the client domain-rule notes only.

        Deliberately NOT the whole vault -- see the module docstring. Kept under the original
        name because `auto_doc` and the (currently uncollected) tests refer to it.
        """
        rules_dir = self.vault_path / self.CLIENT_RULES_DIR
        if not rules_dir.exists():
            logger.warning(
                f"[vault_sync] Client rules directory does not exist: {rules_dir}. "
                f"Falling back to built-in defaults only."
            )
            return ""

        contents = []
        for root, _, files in os.walk(rules_dir):
            for f in files:
                if f.endswith(".md"):
                    try:
                        p = Path(root) / f
                        with open(p, "r", encoding="utf-8", errors="ignore") as file_obj:
                            contents.append(file_obj.read())
                    except Exception as err:
                        logger.warning(f"[vault_sync] Failed to read {f}: {err}")
        return "\n".join(contents)

    @staticmethod
    def _strip_fenced_blocks(text: str) -> str:
        """Remove ``` fenced code blocks before scanning for inline `code` spans.

        Without this, the inline regex `` `([^`]+)` `` pairs the closing backtick of one fence
        with the opening backtick of the next and captures everything between them -- mermaid
        diagrams, frontmatter, whole sections. That was the mechanism behind 36 junk keywords.
        """
        return re.sub(r"```.*?```", " ", text, flags=re.S)

    def load_live_rules(self, force_reload: bool = False) -> Dict[str, Any]:
        """Loads and parses dynamic rules from Obsidian vault markdown notes."""
        if self._cached_rules is not None and not force_reload:
            return self._cached_rules

        raw_text = self._read_all_markdown_contents()

        # 1. Base Default Fallbacks
        keywords: Set[str] = {
            "指示外公差", "指示無き公差", "指示なき公差", "表示外公差", "一般公差", "普通公差",
            "表面粗さ", "仕上精度", "仕上ゲ記号", "粗さの区分", "寸法の区分", "公差の区分",
            "機械加工", "製造加工", "tolerancesunlessotherwise", "unlessotherwisespecified",
            "roughnessrange", "finishsymbol"
        }
        
        patterns: List[str] = [
            r'\b\d+(\.\d+)?S\s*~',
            r'~\s*\d+(\.\d+)?S\b',
            r'^\d+(\.\d+)?S$'
        ]

        upper_left_anchors: Set[str] = {
            "map", "unit no", "unit no.", "part no", "part no.", "part.no",
            "ユニットno", "ユニットno.", "ユニット no", "コードno", "コードno.", "コード no",
            "t. q'ty", "t.q'ty", "stock q'ty", "在庫棚入庫", "総製作個数", "共通番号"
        }

        # 2. Extract Additional Keywords from the client domain-rule notes
        learned: Dict[str, List[str]] = {}
        if raw_text:
            scannable = self._strip_fenced_blocks(raw_text)

            for match in re.finditer(r'`([^`\n]+)`', scannable):
                code_val = match.group(1).strip()
                # A real anchor is a short phrase. The upper bound is what stops a runaway
                # match from re-entering the keyword set as a giant span.
                if not (2 <= len(code_val) <= 60):
                    continue
                if code_val.startswith("http") or code_val.endswith(".py"):
                    continue
                norm_code = code_val.lower().replace(" ", "")
                if any(tok in norm_code for tok in ("公差", "粗さ", "仕上", "加工", "tolerance")):
                    keywords.add(code_val.lower())
                    keywords.add(norm_code)

            learned = self._parse_learned_rules(scannable)

        parsed_rules = {
            "tolerance_keywords": list(keywords),
            "surface_roughness_patterns": patterns,
            "upper_left_anchors": list(upper_left_anchors),
            "learned_dismissals": learned,
        }

        self._cached_rules = parsed_rules
        learned_total = sum(len(v) for v in learned.values())
        logger.info(
            f"[vault_sync] Synchronized live rules from '{self.CLIENT_RULES_DIR}': "
            f"{len(keywords)} tolerance keywords, {len(patterns)} roughness regexes, "
            f"{learned_total} learned dismissal pattern(s) across {len(learned)} categor(ies)."
        )
        return parsed_rules

    @staticmethod
    def _parse_learned_rules(text: str) -> Dict[str, List[str]]:
        """Parse the rule blocks `AutoDocEngine` writes, closing the Pillar 3 -> Pillar 1 loop.

        Pillar 3 writes a note when a pattern is dismissed >= 3 times for a client, but nothing
        ever read it back: this manager only extracted *tolerance* vocabulary, and the
        upper-left anchor list it returns is hardcoded. A learned `title_block` rule therefore
        had no path into the engine and the active-learning flywheel did not close.

        The block shape is fixed by `auto_doc.py`:

            ## Learned Rule — Pattern: `<entity_text>`
            - Client: <client>
            - Category: `<category>`
            - Human Dismissals: <n> confirmed overrides
            - Directive: ...

        Returns `{category: [pattern, ...]}`.
        """
        learned: Dict[str, List[str]] = {}
        block_re = re.compile(
            r"##\s*Learned Rule\s*[—-]\s*Pattern:\s*`([^`\n]+)`"      # the dismissed text
            r"(?:(?!\n##).)*?"                                          # stay inside this block
            r"\*\*Category\*\*:\s*`([^`\n]+)`",                        # its category
            re.S,
        )
        for match in block_re.finditer(text):
            pattern = match.group(1).strip()
            category = match.group(2).strip()
            if not pattern or not category:
                continue
            bucket = learned.setdefault(category, [])
            if pattern not in bucket:
                bucket.append(pattern)
        return learned

    def get_tolerance_keywords(self) -> List[str]:
        return self.load_live_rules().get("tolerance_keywords", [])

    def get_surface_roughness_patterns(self) -> List[str]:
        return self.load_live_rules().get("surface_roughness_patterns", [])

    def get_upper_left_anchors(self) -> List[str]:
        return self.load_live_rules().get("upper_left_anchors", [])

    def get_learned_dismissals(self, category: Optional[str] = None) -> List[str]:
        """Patterns humans have dismissed >= 3 times, from Pillar 3's learned-rule notes.

        `category` filters to one checklist category; omitting it returns every learned
        pattern across all of them.

        Consumers should match these exactly (after normalization), never as substrings.
        These come from `AuditFeedbackDocument.entity_text` -- the precise string a human
        dismissed -- and several are short (`1`, `2A0`). Substring matching would silently
        suppress unrelated content, which is the one failure mode this system cannot detect,
        because nothing measures its false-negative rate.
        """
        learned: Dict[str, List[str]] = self.load_live_rules().get("learned_dismissals", {}) or {}
        if category is not None:
            return list(learned.get(category, []))
        return [p for patterns in learned.values() for p in patterns]

    def get_learned_dismissal_rules(
        self, category: Optional[str] = None
    ) -> List[LearnedDismissal]:
        """The structured form: each pattern carries the category it may act in.

        Prefer this over `get_learned_dismissals`, which returns bare strings and therefore
        cannot tell a caller which pool a pattern is evidence about. The string form is kept
        because it is the shape the vault notes are parsed into and several tests pin it; it is
        not deprecated, it is just narrower.

        Omitting `category` returns every rule, each still carrying its own scope -- so a caller
        that flattens the list is making that choice explicitly rather than by accident.
        """
        learned: Dict[str, List[str]] = self.load_live_rules().get("learned_dismissals", {}) or {}
        rules: List[LearnedDismissal] = []
        for cat, patterns in learned.items():
            if category is not None and cat != category:
                continue
            for pattern in patterns:
                if not pattern:
                    continue
                rules.append(
                    LearnedDismissal(
                        pattern=pattern,
                        category=cat,
                        match_mode=_match_mode_for(pattern),
                    )
                )
        return rules
