"""Session-wide guards for the backend test suite.

Everything here exists to stop a test writing into the working tree. That is not
hypothetical: Stage 0h moved the learned-model artifact out of the vault, and the moment it
did, `test_bundle_save_load_roundtrip` — which had correctly redirected `vault_path` —
started dropping a 133 KB `finding_classifier.joblib` into `services/backend/storage/models/`
instead of into `tmp_path`. The next run then loaded *that* bundle rather than the real one.

A per-test `monkeypatch` fixes one test. This fixes the class.
"""

import os
import tempfile
from pathlib import Path

import pytest

from services.backend.infrastructure.learning import config


@pytest.fixture(autouse=True, scope="session")
def _isolate_learned_model_dir():
    """Point `LEARNED_MODEL_DIR` at a scratch directory for the whole session.

    Autouse and session-scoped on purpose: a test that trains a model should not have to
    remember this, and forgetting it is silent — the write succeeds, the assertion passes,
    and the damage shows up as a stale model on the next unrelated run.

    An individual test may still `monkeypatch.setenv` its own path on top; function-scoped
    monkeypatching wins over this and is restored afterwards.
    """
    with tempfile.TemporaryDirectory(prefix="learned-model-") as scratch:
        previous = os.environ.get(config.MODEL_DIR_ENV)
        os.environ[config.MODEL_DIR_ENV] = scratch
        try:
            yield Path(scratch)
        finally:
            if previous is None:
                os.environ.pop(config.MODEL_DIR_ENV, None)
            else:
                os.environ[config.MODEL_DIR_ENV] = previous
