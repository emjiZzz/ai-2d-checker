"""`eval_corpus validate` — check a draft without installing it.

The annotation loop before this was fill -> `label --from` -> rejection, with no way to check
work in progress. A malformed address discovered after an hour of annotation cost that hour,
and the corpus needs six pairs annotated by hand, so the loop's cost is the schedule.

Two properties matter and both are asserted here:

* it reports **every** problem in one pass, not the first — a validator that stops at the first
  error just makes the same slow loop shorter per iteration; and
* it is **read-only**. `label` stays the only command that can change ground truth, because a
  validator that quietly installed on success would make "check my work" a destructive verb.
"""

import json

import pytest

from services.backend.infrastructure.eval.corpus import GUIDELINE_VERSION

tools_eval_corpus = pytest.importorskip("tools.eval_corpus")


def _draft(tmp_path, **overrides):
    body = {
        "pair_id": "P1",
        "guideline_version": GUIDELINE_VERSION,
        "annotator": "tester",
        "annotated_at": "2026-08-07",
        "notes": "",
        "findings": [],
        "not_findings": [],
    }
    body.update(overrides)
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run(path, pair_id="P1"):
    parser = tools_eval_corpus.build_parser()
    args = parser.parse_args(
        ["validate", "--pair-id", pair_id, "--from", str(path)]
    )
    return args.func(args)


def test_a_missing_file_is_a_clear_failure(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path / "nope.json")


def test_malformed_json_does_not_raise_a_traceback(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        _run(path)

    assert "not valid JSON" in str(excinfo.value)


def test_an_empty_annotator_and_zero_findings_are_both_reported(tmp_path, capsys):
    """One pass, both problems. Reporting only the first would preserve the slow loop."""
    path = _draft(tmp_path, annotator="", findings=[])

    code = _run(path)
    out = capsys.readouterr().out

    assert code == 1
    # Both, in one pass. The unregistered pair id is reported alongside them rather than
    # short-circuiting the schema checks, which is the behaviour under test.
    assert "annotator" in out
    assert "zero findings" in out
    assert "in the manifest" in out


def test_a_stale_guideline_version_is_reported_rather_than_raised(tmp_path, capsys):
    """`PairLabels.from_dict` raises on drift, which is right for the eval path and wrong here:
    an annotator working against an older guideline still needs the rest of their errors."""
    path = _draft(tmp_path, guideline_version="2020-01-01", findings=[])

    code = _run(path)
    out = capsys.readouterr().out

    assert code == 1
    assert "guideline_version" in out
    assert GUIDELINE_VERSION in out


def test_validate_never_writes_the_manifest(tmp_path, monkeypatch):
    """The read-only guarantee, asserted rather than trusted."""
    written = []
    monkeypatch.setattr(
        tools_eval_corpus, "write_manifest", lambda *a, **k: written.append(a)
    )

    path = _draft(tmp_path, annotator="", findings=[])
    _run(path)

    assert written == []
