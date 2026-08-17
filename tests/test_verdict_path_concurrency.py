"""The verdict path must not block the event loop, and must not race itself.

**The symptom this file exists for**, reported 2026-08-17: every supervisor verdict produced a
"Connection Lost" and a reconnect in the desktop app — reliably, on a single click, not only
under rapid clicking.

The chain, measured rather than reasoned about:

1. `connectionStore.checkHealth` polls `/health` every 5 s and aborts at **3 s**. Any event-loop
   block longer than that *is* a disconnect, whatever caused it.
2. `review_violation` queues `train_from_feedback` via `BackgroundTasks`, which runs an async
   task **on the event loop**.
3. `train_from_feedback` called `build_bundle` synchronously. Measured on the live corpus at 112
   verdict labels: **7.2 s, every call.**

**It began when the learned verdict head activated, not when any code changed.** `_cv_accuracy`
— a 3-fold `StratifiedKFold` fitting a model per fold and calling `predict_one` per test row —
sits inside the branch that only runs once `minority_share >= MIN_MINORITY_SHARE`. Below that
threshold `build_bundle` abstains and returns in milliseconds. The corpus crossed 0.30 (it is
0.3661), the head switched on, and the cost arrived with the milestone. Nothing flagged it
because nothing had changed.
"""
from __future__ import annotations

import asyncio
import inspect
import time

from services.backend.infrastructure.learning import model_holder, trainer
from services.backend.infrastructure.retrieval import service as retrieval_service
from services.backend.infrastructure.retrieval import store as store_module

# No module-level `pytest.mark.asyncio`: `asyncio_mode = auto` picks up the async tests, and a
# blanket mark warns on every synchronous one in the file.

#: How long the fake retrain pretends to compute. Comfortably longer than the tolerance below,
#: so a regression to inline execution cannot pass by being fast on a quiet machine.
FAKE_TRAIN_SECONDS = 0.5

#: The event loop may stall by this much and no more. Generous — the real budget is the desktop
#: app's 3 s health timeout — but far below `FAKE_TRAIN_SECONDS`, which is what makes it a test.
MAX_TOLERATED_STALL = 0.2

#: Each of these write paths puts two files in place (a payload and its manifest/meta), and both
#: halves have to be renamed rather than written open — a fresh payload beside a stale manifest
#: is the same corruption as a half-written payload.
_FILES_NEEDING_ATOMIC_WRITE = 2


async def _worst_stall(stop: asyncio.Event) -> float:
    """Heartbeat: the largest gap between when a 50 ms sleep should end and when it does."""
    worst = 0.0
    while not stop.is_set():
        started = time.perf_counter()
        await asyncio.sleep(0.05)
        worst = max(worst, time.perf_counter() - started - 0.05)
    return worst


async def test_a_retrain_does_not_block_the_event_loop(monkeypatch):
    """The regression guard for the reported disconnect.

    Asserted on **observed loop responsiveness** rather than on the presence of
    `asyncio.to_thread` in the source, because the property that matters to a user is whether
    `/health` gets answered — and a future refactor could keep the call and still block, or drop
    it and still be fine.
    """
    class _FakeDocs:
        @staticmethod
        def find_all():
            class _Q:
                @staticmethod
                async def to_list():
                    return []
            return _Q()

    monkeypatch.setattr(
        "services.backend.domain.models.audit_feedback.AuditFeedbackDocument", _FakeDocs
    )

    def slow_synchronous_build(docs):
        time.sleep(FAKE_TRAIN_SECONDS)   # stands in for build_bundle's sklearn work
        return model_holder._empty_bundle()

    monkeypatch.setattr(trainer, "build_bundle", slow_synchronous_build)
    monkeypatch.setattr(trainer, "save_bundle", lambda bundle: None)
    monkeypatch.setattr(trainer, "_write_model_card", lambda bundle: None)
    monkeypatch.setattr(
        trainer.LearnedModelHolder, "get_instance", classmethod(lambda cls: _FakeHolder())
    )

    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_worst_stall(stop))

    started = time.perf_counter()
    await trainer.train_from_feedback()
    elapsed = time.perf_counter() - started

    stop.set()
    worst = await heartbeat

    assert elapsed >= FAKE_TRAIN_SECONDS, "the fake work did not actually run"
    assert worst < MAX_TOLERATED_STALL, (
        f"the event loop stalled {worst:.2f}s during a retrain. At the real corpus size this "
        f"work takes ~7s, which exceeds the desktop app's 3s /health timeout and shows up as "
        f"'Connection Lost' on every verdict."
    )


class _FakeHolder:
    def reload(self) -> None:
        pass

    def status(self) -> dict:
        return {"verdict_ready": False}


async def test_two_retrains_do_not_overlap(monkeypatch):
    """Both would fit a model and write the same two files, from two worker threads."""
    concurrent = 0
    peak = 0

    class _FakeDocs:
        @staticmethod
        def find_all():
            class _Q:
                @staticmethod
                async def to_list():
                    return []
            return _Q()

    monkeypatch.setattr(
        "services.backend.domain.models.audit_feedback.AuditFeedbackDocument", _FakeDocs
    )

    def counting_build(docs):
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        time.sleep(0.1)
        concurrent -= 1
        return model_holder._empty_bundle()

    monkeypatch.setattr(trainer, "build_bundle", counting_build)
    monkeypatch.setattr(trainer, "save_bundle", lambda bundle: None)
    monkeypatch.setattr(trainer, "_write_model_card", lambda bundle: None)
    monkeypatch.setattr(
        trainer.LearnedModelHolder, "get_instance", classmethod(lambda cls: _FakeHolder())
    )

    await asyncio.gather(*(trainer.train_from_feedback() for _ in range(4)))
    assert peak == 1, f"{peak} retrains ran at once; they write the same bundle files"


def test_the_index_is_written_atomically():
    """Three files that must come from one build.

    `review_violation` rebuilds `lessons` on every verdict through `asyncio.to_thread`, so two
    verdicts genuinely run `VectorStore.write` in parallel threads. In-place writes could pair
    one run's matrix with another run's records — which `load()` detects as STALE, silently
    dropping the audit path to substring matching.
    """
    source = inspect.getsource(store_module.VectorStore.write)
    assert "os.replace" in source, "index files must be renamed into place, not written in place"
    assert source.count("os.replace") >= _FILES_NEEDING_ATOMIC_WRITE, (
        "matrix and records both need it"
    )
    assert "os.replace" in inspect.getsource(store_module.Manifest.dump)


def test_the_model_bundle_is_written_atomically():
    """`LearnedModelHolder.reload()` reads these from a different thread than the writer."""
    source = inspect.getsource(model_holder.save_bundle)
    assert source.count("os.replace") >= _FILES_NEEDING_ATOMIC_WRITE, (
        "the joblib payload and the meta both need it"
    )


def test_reloading_the_bundle_never_publishes_a_null_window():
    """Clearing `_bundle` before loading lets a concurrent reader see the model as absent.

    Inference runs on the event loop while a retrain reloads from a worker thread, so that window
    is reachable — and it degrades silently: the comparison just skips the learned adjustment.
    """
    source = inspect.getsource(model_holder.LearnedModelHolder.reload)
    assert "self._bundle = None" not in source, (
        "reload clears the bundle before repopulating it, which is the null window"
    )
    assert "_read_bundle" in source


def test_lessons_rebuilds_are_serialised():
    source = inspect.getsource(retrieval_service.rebuild_lessons_index)
    assert "_rebuild_lock" in source, (
        "every supervisor verdict rebuilds this index; without a lock two verdicts write it at once"
    )
