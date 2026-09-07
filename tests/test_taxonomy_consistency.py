"""
Cross-check that the backend taxonomy (services/backend/infrastructure/audit/comparison/
taxonomy.py) and its hand-mirrored frontend copy (apps/desktop/src/utils/
comparisonTaxonomy.ts) stay identical (docs/checklist-taxonomy-grouping-implementation-
plan.md, Phase 8). There is no runtime type-sharing mechanism between the two languages
in this repo, so nothing else enforces this — this is a lightweight text-parse of the
.ts file, not a full TypeScript parser, deliberately kept simple since the .ts file's
structure is a plain, consistently-formatted object literal.
"""
import re
from pathlib import Path

from services.backend.infrastructure.audit.comparison import taxonomy as backend_taxonomy

FRONTEND_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[1]
    / "apps" / "desktop" / "src" / "utils" / "comparisonTaxonomy.ts"
)


def _read_frontend_source() -> str:
    return FRONTEND_TAXONOMY_PATH.read_text(encoding="utf-8")


def _parse_frontend_taxonomy(source: str) -> dict[str, list[tuple[str, str]]]:
    """Extracts {category: [(key, label), ...]} from COMPARISON_TAXONOMY's object literal."""
    obj_match = re.search(
        r"COMPARISON_TAXONOMY:\s*Record<string,\s*FeatureItem\[\]>\s*=\s*\{(.*?)\n\};",
        source, re.DOTALL,
    )
    assert obj_match, "Could not locate COMPARISON_TAXONOMY object literal in comparisonTaxonomy.ts"
    body = obj_match.group(1)

    result: dict[str, list[tuple[str, str]]] = {}
    for cat_match in re.finditer(r"(\w+):\s*\[(.*?)\n\s*\],", body, re.DOTALL):
        category = cat_match.group(1)
        items_block = cat_match.group(2)
        items = re.findall(r'key:\s*"([^"]+)",\s*label:\s*"([^"]+)"', items_block)
        result[category] = items
    return result


def _parse_frontend_scalar(source: str, const_name: str) -> str:
    m = re.search(rf'{const_name}\s*=\s*"([^"]+)"', source)
    assert m, f"Could not locate {const_name} in comparisonTaxonomy.ts"
    return m.group(1)


def _parse_frontend_deferred_keys(source: str) -> set[str]:
    m = re.search(r"DEFERRED_FEATURE_KEYS[^=]*=\s*new Set\(\[(.*?)\]\)", source, re.DOTALL)
    assert m, "Could not locate DEFERRED_FEATURE_KEYS in comparisonTaxonomy.ts"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def test_frontend_taxonomy_file_exists():
    assert FRONTEND_TAXONOMY_PATH.exists(), f"Expected {FRONTEND_TAXONOMY_PATH} to exist"


def test_category_keys_match():
    source = _read_frontend_source()
    frontend = _parse_frontend_taxonomy(source)
    assert set(frontend.keys()) == set(backend_taxonomy.TAXONOMY.keys())


def test_feature_keys_and_order_match_per_category():
    source = _read_frontend_source()
    frontend = _parse_frontend_taxonomy(source)
    for category, backend_items in backend_taxonomy.TAXONOMY.items():
        backend_keys = [item.key for item in backend_items]
        frontend_keys = [key for key, _label in frontend.get(category, [])]
        assert frontend_keys == backend_keys, (
            f"Feature key list/order mismatch for category '{category}': "
            f"backend={backend_keys} frontend={frontend_keys}"
        )


def test_feature_labels_match_per_category():
    source = _read_frontend_source()
    frontend = _parse_frontend_taxonomy(source)
    for category, backend_items in backend_taxonomy.TAXONOMY.items():
        backend_labels = {item.key: item.label for item in backend_items}
        frontend_labels = {key: label for key, label in frontend.get(category, [])}
        assert frontend_labels == backend_labels, f"Label mismatch for category '{category}'"


def test_other_feature_key_and_label_match():
    source = _read_frontend_source()
    assert _parse_frontend_scalar(source, "OTHER_FEATURE_KEY") == backend_taxonomy.OTHER_FEATURE_KEY
    assert _parse_frontend_scalar(source, "OTHER_FEATURE_LABEL") == backend_taxonomy.OTHER_FEATURE_LABEL


def test_deferred_features_match():
    source = _read_frontend_source()
    assert _parse_frontend_deferred_keys(source) == backend_taxonomy.DEFERRED_FEATURES
