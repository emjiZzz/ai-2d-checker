---
tags: [gotcha, testing, learning, storage, gitignore]
status: fixed
cache-version: n/a — test isolation and artifact location, not engine behaviour
date: 2026-08-05
---

# Gotcha — Moving an Artifact Broke Its Test Isolation

> [!WARNING] A test that redirected the *old* location kept passing while writing 133 KB
> into the working tree, and the next run loaded that file instead of the real model.

## What happened

Stage 0h moved the learned-model bundle out of the gitignored vault. Before the move,
`model_holder.learned_model_dir()` resolved through `VaultSyncManager.get_instance().vault_path`,
so a test could contain every write with one line:

```python
monkeypatch.setattr(VaultSyncManager.get_instance(), "vault_path", tmp_path)
```

After the move it resolves `LEARNED_MODEL_DIR` → `services/backend/storage/models/` and never
consults `vault_path` at all. `test_bundle_save_load_roundtrip` still redirected the vault, so
it still *looked* isolated — and dropped a real trained bundle into the repo. It failed only
on its final assertion (the file was not where it expected), which is luck: had it asserted
`holder.bundle is not None` and stopped, it would have passed green while poisoning the next
run, because `LearnedModelHolder` would then load the test's 12-document model instead of the
real 16-label one.

## Why the fix is a conftest, not a monkeypatch

Patching the one test fixes the one test. The hazard is structural: **any** future test that
calls `save_bundle` without knowing about the new env variable writes into the working tree,
and the failure is silent — the write succeeds, the assertion passes, and the damage appears
later as a stale model in an unrelated run.

`tests/conftest.py` now points `LEARNED_MODEL_DIR` at a session-scoped temporary directory,
autouse. A test that wants its own path still wins: function-scoped `monkeypatch.setenv`
overrides it and is restored afterwards.

## The gitignore rule shape, which is not obvious

Stage 0h also needs the `.meta.json` **tracked** while the `.joblib` beside it stays ignored.
The first attempt did not work:

```gitignore
services/backend/storage/          # excludes the DIRECTORY
!services/backend/storage/models/  # unreachable
```

Git never descends into an excluded directory, so no `!` rule beneath one can ever fire — no
matter what order the rules appear in. The parent has to exclude *contents* instead:

```gitignore
services/backend/storage/*
!services/backend/storage/models/
services/backend/storage/models/*
!services/backend/storage/models/*.meta.json
```

Verify with `git check-ignore -v <path>`; a line beginning `!` means the path is **not**
ignored. `tests/test_learned_model_location.py` asserts the rule shape directly, because the
failure mode is that the metadata quietly never becomes committable and nobody notices.

## Unrelated finding, surfaced by the same check

`git check-ignore` reported `services/backend/storage/secure/.api-token` as not ignored.
That is **not** a regression from this change — the file is *already tracked*, committed in
`6a30319`, and `.gitignore` has a comment saying exactly that. `--no-index` confirms the
rules would exclude it. Worth deciding on separately: `git rm --cached` would untrack it and
the token regenerates on startup, but it remains in history, and purging history is a
different and destructive operation.

## The transferable lesson

**When you change where something is stored, re-check everything that was isolating it.**
Test isolation is usually written against the *mechanism* of resolution, not the *fact* of
it — so moving the resolution silently converts a contained test into one that writes to
your repo. Grep for every fixture that redirected the old path, not just the code that read
it.

## See also

- [[Gotcha - Learned Corrections Model and Post-Cache Inference]] — the rest of this model's
  wiring
- [[00 - AI Maturity Status]] — Stage 0h, and why a model that cannot be committed blocks
  rung 3
