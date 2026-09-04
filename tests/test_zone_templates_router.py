"""
Zone-templates router — the global default (fallback) endpoints.

Focus: the single-default invariant (setting one default clears any prior one) and the 404
on an unknown signature. DB access is fully mocked, so this runs offline.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from services.backend.api.routers.zone_templates import (
    SetDefaultRequest,
    get_default_zone_template,
    set_default_zone_template,
)
from services.backend.domain.models.zone_template import ZoneTemplateDocument

pytestmark = pytest.mark.asyncio


class _MockField:
    """Makes `ZoneTemplateDocument.field == x` / `!= x` evaluable without init_beanie (same
    pattern as test_rooms.py). The result is only ever fed to a mocked find/find_one."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ne__(self, other):
        return ("ne", self.name, other)


@pytest.fixture(autouse=True)
def mock_zone_fields(monkeypatch):
    monkeypatch.setattr(
        ZoneTemplateDocument, "get_pymongo_collection", classmethod(lambda cls: MagicMock())
    )
    monkeypatch.setattr(ZoneTemplateDocument, "signature", _MockField("signature"), raising=False)
    monkeypatch.setattr(ZoneTemplateDocument, "is_default", _MockField("is_default"), raising=False)


def _tpl(signature: str, is_default: bool = False) -> ZoneTemplateDocument:
    return ZoneTemplateDocument(signature=signature, name=signature, zones={}, is_default=is_default)


class _AsyncIter:
    """Minimal async-iterable so `async for other in ZoneTemplateDocument.find(...)` works offline."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


async def test_setting_default_clears_the_previous_default(monkeypatch):
    target = _tpl("aspect-1.414", is_default=False)
    prior = _tpl("aspect-2.000", is_default=True)

    monkeypatch.setattr(ZoneTemplateDocument, "find_one", AsyncMock(return_value=target))
    monkeypatch.setattr(
        ZoneTemplateDocument, "find", classmethod(lambda cls, *a, **k: _AsyncIter([prior]))
    )
    monkeypatch.setattr(ZoneTemplateDocument, "save", AsyncMock())

    resp = await set_default_zone_template("aspect-1.414", SetDefaultRequest(is_default=True))

    assert resp.success is True
    assert resp.data.is_default is True
    assert target.is_default is True   # target is now the default
    assert prior.is_default is False   # single-default invariant: the old default was cleared


async def test_clearing_default_does_not_touch_other_templates(monkeypatch):
    target = _tpl("aspect-1.414", is_default=True)
    find = classmethod(lambda cls, *a, **k: _AsyncIter([_tpl("other")]))  # should never be iterated

    monkeypatch.setattr(ZoneTemplateDocument, "find_one", AsyncMock(return_value=target))
    monkeypatch.setattr(ZoneTemplateDocument, "find", find)
    monkeypatch.setattr(ZoneTemplateDocument, "save", AsyncMock())

    resp = await set_default_zone_template("aspect-1.414", SetDefaultRequest(is_default=False))

    assert resp.data.is_default is False
    assert target.is_default is False


async def test_set_default_on_unknown_signature_404s(monkeypatch):
    monkeypatch.setattr(ZoneTemplateDocument, "find_one", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await set_default_zone_template("nope", SetDefaultRequest(is_default=True))

    assert exc.value.status_code == 404


async def test_get_default_returns_null_when_none_set(monkeypatch):
    monkeypatch.setattr(ZoneTemplateDocument, "find_one", AsyncMock(return_value=None))

    resp = await get_default_zone_template()

    assert resp.success is True
    assert resp.data is None
