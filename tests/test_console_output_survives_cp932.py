"""Operator-facing console output must survive cp932, the narrowest encoding in this stack.

`Gotcha - Our Own Punctuation Broke on the cp932 Console` established the rule and it was broken
again anyway: `tools/label_status.py` printed a U+2014 EM DASH on line 1 and died with
UnicodeEncodeError on the default Windows console — taking the *entire* report with it, including
the class-balance warning that is the tool's whole reason for existing.

That is the shape worth guarding. The failure is not cosmetic: it happens at the first `print`, so
a tool whose job is to report a safety-critical number reports nothing at all, on the platform the
product actually ships to, while passing every test on a UTF-8 CI runner.

Scope, deliberately narrow. Only the literals that reach a terminal. Docstrings, comments and
Japanese *data* are exempt — the drawing text this system exists to process is the payload, is
written with explicit `encoding="utf-8"`, and was never the problem. This guards our own
decorations, not user content.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# CLI entry points whose output an operator reads on a raw console.
CONSOLE_TOOLS = [
    "tools/label_status.py",
    "tools/eval.py",
    "tools/standards_scan.py",
    # Added 2026-08-14 after it crashed for real: `retrieval_eval.py worksheet` printed an em
    # dash while explaining how to supply queries, and died with UnicodeEncodeError on a cp932
    # console. It was also the only tool in `tools/` with no `reconfigure(errors="replace")`
    # guard, so both layers failed at once. Both are fixed; this pins the literal half.
    "tools/retrieval_eval.py",
]

# NOT listed, deliberately, and worth knowing about: `tools/eval_corpus.py` carries 3 cp932-unsafe
# print literals but DOES have the reconfigure guard, so it degrades instead of crashing. Adding it
# here would fail today. It is the corpus/labelling tool, i.e. on the project's critical path, so
# the literals are worth cleaning up — but that is its own change, not a rider on this one.


def _print_literals(path: pathlib.Path):
    """Every string constant that is an argument to a bare `print(...)` call.

    An AST walk rather than a text scan, for the reason `test_no_fake_ai_capability.py` gives:
    comments and docstrings are commentary and must not be policed. This sees only executable
    arguments — including the pieces of an f-string, which is where the em dashes actually were.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        is_print = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        )
        if not is_print:
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    yield sub.lineno, sub.value


@pytest.mark.parametrize("rel", CONSOLE_TOOLS)
def test_printed_literals_are_cp932_encodable(rel):
    path = REPO_ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")

    offenders = []
    for lineno, text in _print_literals(path):
        try:
            text.encode("cp932")
        except UnicodeEncodeError:
            bad = sorted({c for c in text if _breaks_cp932(c)})
            offenders.append(f"{rel}:{lineno} contains {[hex(ord(c)) for c in bad]}")

    assert not offenders, (
        "Console output must be cp932-encodable — it crashes the whole tool on a default Windows "
        "console, at the first print. Use ASCII for punctuation we add:\n  "
        + "\n  ".join(offenders)
    )


def _breaks_cp932(char: str) -> bool:
    try:
        char.encode("cp932")
    except UnicodeEncodeError:
        return True
    return False


def test_the_guard_can_actually_fail():
    """A guard whose failure path has never run is not known to work.

    This vault has a note on exactly that (`Gotcha - A Guard Test's Failure Path Had Never Run`),
    so the em dash is asserted to be the thing cp932 rejects, rather than assumed.
    """
    assert _breaks_cp932("—")      # EM DASH — the character that broke label_status.py
    assert _breaks_cp932("·")      # MIDDLE DOT — the original offender in the gotcha note
    assert not _breaks_cp932("-")
    assert not _breaks_cp932("あ")  # Japanese data is fine and must stay exempt
