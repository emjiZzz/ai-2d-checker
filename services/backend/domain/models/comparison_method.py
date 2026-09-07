"""The name of the comparison method, and the one legacy alias for it.

Its own module because the name is written into the room document, the comparison request, the
room response and the cache filename. While it was a repeated string literal there was nothing
to rename, only occurrences to find, which is how the old name outlived its accuracy.

The method is called `deterministic` because it contains no retrieval and no LLM. It was `rag`,
tolerable while that was the default of four methods; ADR-006 removed the other three and left
the name as the system's whole vocabulary for what it does. Agents kept inferring a retrieval
pipeline from it.

`"rag"` is accepted on input everywhere and normalised, permanently rather than as a migration
window: room documents written before the rename still say it, cached
`physical_comparison_results` payloads embed it in their own JSON, and the two names denote the
same engine, so there is no version of this system that should reject it. Normalising on the way
IN (a `mode="before"` validator) is what leaves every downstream consumer one spelling.
"""

from typing import Any, Final, Literal

#: The only comparison method. A `Literal` of one, so adding a second is a deliberate edit here.
ComparisonMethodName = Literal["deterministic"]

DETERMINISTIC: Final[str] = "deterministic"

#: Accepted on input and folded into `DETERMINISTIC`. See the module docstring — permanent.
LEGACY_METHOD_ALIASES: Final[frozenset[str]] = frozenset({"rag"})


def normalize_comparison_method(value: Any) -> Any:
    """Folds a legacy method name into the current one. Non-strings pass through untouched.

    Deliberately does NOT reject unknown strings — that is the `Literal`'s job, and doing it
    here would produce a validation error naming this function instead of the field.
    """
    if isinstance(value, str) and value in LEGACY_METHOD_ALIASES:
        return DETERMINISTIC
    return value
