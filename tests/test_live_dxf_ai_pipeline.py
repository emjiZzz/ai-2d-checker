"""
test_live_dxf_ai_pipeline.py — Unit tests for Live Real-DXF AI Vision pipeline.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services.backend.domain.models.drawing_document import DrawingDocument
from services.backend.infrastructure.audit.comparison.live_dxf_orchestrator import (
    resolve_physical_dxf_path,
    parse_live_dxf_file,
    perform_live_dxf_ai_comparison,
)


@pytest.mark.asyncio
async def test_resolve_physical_dxf_path_dxf(tmp_path):
    """Verifies physical DXF path resolution for a .dxf file."""
    fake_dxf = tmp_path / "sample.dxf"
    fake_dxf.write_text("0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")

    drawing = MagicMock()
    drawing.file_name = "sample.dxf"
    drawing.file_path = "sample.dxf"
    drawing.file_hash = "hash123"
    drawing.file_size_bytes = 100
    drawing.format = "dxf"

    with patch("services.backend.infrastructure.audit.comparison.live_dxf_orchestrator.get_storage_root", return_value=tmp_path):
        dxf_path, is_temp = await resolve_physical_dxf_path(drawing)
        assert dxf_path == fake_dxf
        assert is_temp is False


@pytest.mark.asyncio
async def test_resolve_physical_dxf_path_dwg_conversion(tmp_path):
    """Verifies on-the-fly DWG->DXF conversion trigger when drawing format is dwg."""
    fake_dwg = tmp_path / "sample.dwg"
    fake_dwg.write_bytes(b"AC1032_FAKE_DWG_HEADER")

    fake_temp_dxf = tmp_path / "temp" / "sample.dxf"
    fake_temp_dxf.parent.mkdir(parents=True, exist_ok=True)
    fake_temp_dxf.write_text("0\nEOF\n", encoding="utf-8")

    drawing = MagicMock()
    drawing.file_name = "sample.dwg"
    drawing.file_path = "sample.dwg"
    drawing.file_hash = "hash456"
    drawing.file_size_bytes = 200
    drawing.format = "dwg"

    mock_converter = MagicMock()
    mock_converter.convert_dwg_to_dxf = AsyncMock(return_value=fake_temp_dxf)

    with patch("services.backend.infrastructure.audit.comparison.live_dxf_orchestrator.get_storage_root", return_value=tmp_path), \
         patch("services.backend.infrastructure.audit.comparison.live_dxf_orchestrator.ODAConverter", return_value=mock_converter):
        dxf_path, is_temp = await resolve_physical_dxf_path(drawing)
        assert dxf_path == fake_temp_dxf
        assert is_temp is True
        mock_converter.convert_dwg_to_dxf.assert_called_once()


def test_parse_live_dxf_file(tmp_path):
    """Verifies live parsing of physical .dxf file via DXFParser/ezdxf wrapper."""
    fake_dxf = tmp_path / "test.dxf"
    fake_dxf.write_text("0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")

    mock_parser = MagicMock()
    mock_parser.parse_file.return_value = (
        [{"handle": "1A", "type": "TEXT", "layer": "0", "text": "MAIN VIEW"}],
        [{"name": "0"}],
        {"lines": 0},
        {"title": "Test Drawing"}
    )

    with patch("services.backend.infrastructure.audit.comparison.live_dxf_orchestrator.DXFParser", return_value=mock_parser):
        entities, metadata = parse_live_dxf_file(fake_dxf)
        assert len(entities) == 1
        assert entities[0].id == "1A"
        assert entities[0].entity_type == "text"
        assert metadata["title"] == "Test Drawing"
