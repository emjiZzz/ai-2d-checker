"""
test_pipeline_runner.py — Unit test suite for ModularComparisonPipeline.
"""

import pytest
from services.backend.infrastructure.audit.comparison.pipeline_runner import (
    ModularComparisonPipeline,
    ExtractorStage,
    CandidateStage,
    VerifierStage,
    FormatterStage,
)


class MockStageA:
    def execute(self, context: dict) -> dict:
        return {"extracted_count": 42}


class MockStageB:
    def execute(self, context: dict) -> dict:
        count = context.get("extracted_count", 0)
        return {"final_score": count * 2}


def test_pipeline_runner_sequence():
    pipeline = ModularComparisonPipeline()
    pipeline.add_stage(MockStageA()).add_stage(MockStageB())

    result = pipeline.run({"reference_id": "ref1", "revision_id": "rev1"})

    assert result["extracted_count"] == 42
    assert result["final_score"] == 84
    assert len(result["stage_logs"]) == 2
    assert result["stage_logs"][0]["stage"] == "MockStageA"
    assert result["stage_logs"][1]["stage"] == "MockStageB"


def test_concrete_pipeline_stages():
    pipeline = ModularComparisonPipeline()
    pipeline.add_stage(ExtractorStage())
    pipeline.add_stage(CandidateStage())
    pipeline.add_stage(VerifierStage())
    pipeline.add_stage(FormatterStage())

    ctx = {
        "reference_drawing_id": "dwg_ref_100",
        "drawing_id": "dwg_rev_101",
        "candidates": [],
        "verified_markings": [],
    }

    res = pipeline.run(ctx)

    assert res["extraction_status"] == "completed"
    assert res["candidate_count"] == 0
    assert res["verified_count"] == 0
    assert res["formatting_status"] == "completed"
    assert len(res["stage_logs"]) == 4
