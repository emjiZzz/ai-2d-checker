"""
Live Obsidian Vault-to-Runtime Sync Manager (Pillar 1).

Reads markdown notes in the Obsidian Second Brain vault (`docs/vault/`) at runtime,
extracting live client domain rules, CAD tolerance keywords, surface roughness regexes,
and zone anchors to inject into backend RAG filters and LLM prompts.
"""

import os
import re
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

    def _read_all_markdown_contents(self) -> str:
        """Reads and concatenates all Markdown files in the vault."""
        if not self.vault_path.exists():
            logger.warning(f"[vault_sync] Vault path does not exist: {self.vault_path}")
            return ""

        contents = []
        for root, _, files in os.walk(self.vault_path):
            for f in files:
                if f.endswith(".md"):
                    try:
                        p = Path(root) / f
                        with open(p, "r", encoding="utf-8", errors="ignore") as file_obj:
                            contents.append(file_obj.read())
                    except Exception as err:
                        logger.warning(f"[vault_sync] Failed to read {f}: {err}")
        return "\n".join(contents)

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

        # 2. Extract Additional Keywords from Vault Markdown Notes
        if raw_text:
            # Look for bullet points under tolerance headers or code blocks
            for match in re.finditer(r'`([^`]+)`', raw_text):
                code_val = match.group(1).strip()
                if len(code_val) >= 2 and not code_val.startswith("http") and not code_val.endswith(".py"):
                    norm_code = code_val.lower().replace(" ", "")
                    if any(tok in norm_code for tok in ("公差", "粗さ", "仕上", "加工", "tolerance")):
                        keywords.add(code_val.lower())
                        keywords.add(norm_code)

        parsed_rules = {
            "tolerance_keywords": list(keywords),
            "surface_roughness_patterns": patterns,
            "upper_left_anchors": list(upper_left_anchors),
        }

        self._cached_rules = parsed_rules
        logger.info(f"[vault_sync] Successfully synchronized live rules from Obsidian Vault: {len(keywords)} tolerance keywords, {len(patterns)} roughness regexes.")
        return parsed_rules

    def get_tolerance_keywords(self) -> List[str]:
        return self.load_live_rules().get("tolerance_keywords", [])

    def get_surface_roughness_patterns(self) -> List[str]:
        return self.load_live_rules().get("surface_roughness_patterns", [])

    def get_upper_left_anchors(self) -> List[str]:
        return self.load_live_rules().get("upper_left_anchors", [])
