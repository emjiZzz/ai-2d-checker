"""Per-user separation of workspaces and uploads on a shared backend.

The prototype is deployed to one LAN backend serving ~21 engineers, and each tester's uploads
should not clutter (or be confused with) everybody else's. `Room.created_by` and
`DrawingDocument.uploaded_by` carry the owner; `?mine=true` narrows each list.

**This is separation, not access control, and the tests say so on purpose.**
The identity is `X-Engineer-Name`: a name picked from a dropdown with no password, sent by the
client, on a backend where every installed app holds the same shared API bearer token. Anyone can
send any name, and every by-id route still serves any record to any caller. If someone later reads
these tests as proof of confidentiality, `test_identity_is_not_authenticated` is the correction.

**`None` means SHARED, not orphaned.** Rows predating these fields are the pre-loaded corpus
pairs every tester works on, so the filter deliberately keeps them. Dropping them would empty
every workspace at once, which is worse than the leak it would close.
"""

from __future__ import annotations

import pytest

from services.backend.api.dependencies import resolve_username


class TestIdentityResolution:
    def test_no_headers_at_all_yields_no_owner(self) -> None:
        """An api-token-only caller (tooling, tests, curl) creates SHARED records."""
        assert resolve_username(None, None) is None

    def test_engineer_name_is_used_when_there_is_no_session(self) -> None:
        # The prototype case: login is skipped, so no session token ever exists.
        assert resolve_username(None, "Raysan") == "Raysan"

    def test_a_verified_session_wins_over_the_engineer_header(self, monkeypatch) -> None:
        """A full build must not have a spoofable header competing with its real identity."""
        import services.backend.core.auth as auth

        monkeypatch.setattr(auth, "verify_session_token", lambda _t: {"username": "real.user"})
        assert resolve_username("a-valid-token", "Impostor") == "real.user"

    def test_an_invalid_session_falls_back_rather_than_raising(self, monkeypatch) -> None:
        """Non-raising by contract: these routes authenticate on the bearer token, not this."""
        import services.backend.core.auth as auth

        def _boom(_t):
            raise ValueError("expired")

        monkeypatch.setattr(auth, "verify_session_token", _boom)
        assert resolve_username("rubbish", "Raysan") == "Raysan"

    def test_blank_and_whitespace_names_are_not_owners(self) -> None:
        # An empty-string owner would match nothing and silently hide a tester's own work.
        for value in ("", "   ", "\t\n"):
            assert resolve_username(None, value) is None

    def test_a_name_is_trimmed_and_bounded(self) -> None:
        # A client-supplied header must not become a 10 KB `created_by`.
        assert resolve_username(None, "  Raysan  ") == "Raysan"
        assert len(resolve_username(None, "x" * 5000)) == 64

    def test_an_unresolved_fastapi_header_object_is_not_a_name(self) -> None:
        """Router functions here are also called DIRECTLY from tests, not only through FastAPI.

        In that case the parameter still holds the unresolved `Header(...)` default -- truthy, and
        with no `.strip`. A truthiness check raised AttributeError inside the identity lookup, and
        the upload route turned a caller's 400 into a 500. Caught by
        `test_drawings_router_error_handling`; pinned here so the cause is findable.
        """
        from fastapi import Header

        sentinel = Header(None, alias="X-Engineer-Name")
        assert resolve_username(None, sentinel) is None
        assert resolve_username(sentinel, sentinel) is None

    def test_identity_is_not_authenticated(self) -> None:
        """The property this whole mechanism does NOT have.

        Two different callers asserting two different names both succeed, because nothing verifies
        the claim. This test exists to be read, not to catch a regression: if per-user privacy ever
        needs to be real, it needs a login, and prototype mode removed the login on purpose.
        """
        assert resolve_username(None, "Raysan") == "Raysan"
        assert resolve_username(None, "SomebodyElse") == "SomebodyElse"


class TestOwnerFilter:
    """The list rule, as a pure function of owner values.

    Mirrors what `GET /rooms?mine=true` and `GET /drawings?mine=true` do, so the SHARED-means-None
    decision is pinned somewhere a reader will find it, without standing up beanie and Mongo.
    """

    @staticmethod
    def _visible(owners: list[str | None], viewer: str) -> list[str | None]:
        return [o for o in owners if o == viewer or o is None]

    def test_a_tester_sees_their_own_and_the_shared_ones(self) -> None:
        owners = ["Raysan", "Erik", None, "Raysan", "Janzen"]
        assert self._visible(owners, "Raysan") == ["Raysan", None, "Raysan"]

    def test_a_tester_does_not_see_another_testers_uploads(self) -> None:
        assert "Erik" not in self._visible(["Erik", "Raysan"], "Raysan")

    def test_the_shared_corpus_is_visible_to_everyone(self) -> None:
        """The deliberate hole. Pre-loaded pairs have no owner and must reach every tester."""
        for viewer in ("Raysan", "Erik", "Janzen"):
            assert self._visible([None, None], viewer) == [None, None]

    def test_a_tester_with_nothing_of_their_own_still_sees_the_corpus(self) -> None:
        # Otherwise a fresh tester opens the app to an empty workspace and nothing to mark.
        assert self._visible(["Erik", None], "NewPerson") == [None]


def test_the_drawing_model_defaults_to_shared() -> None:
    """A drawing created without an uploader is SHARED, which is what tooling produces."""
    from services.backend.domain.models.drawing_document import DrawingDocument

    field = DrawingDocument.model_fields["uploaded_by"]
    assert field.default is None


def test_ingestion_accepts_an_uploader_and_defaults_to_shared() -> None:
    """Pinned because the default is what keeps every existing caller working.

    `process_ingestion` is called by the upload route, by tests, and by tooling. Making the
    parameter required would have broken all but the first.
    """
    import inspect

    from services.backend.infrastructure.ingestion.drawing_ingestion_service import (
        DrawingIngestionService,
    )

    sig = inspect.signature(DrawingIngestionService.process_ingestion)
    assert "uploaded_by" in sig.parameters
    assert sig.parameters["uploaded_by"].default is None


@pytest.mark.parametrize("router", ["rooms", "drawings"])
def test_both_list_routes_expose_the_same_opt_in_filter(router: str) -> None:
    """One rule, two routers, spelled the same way.

    They cannot share an implementation across two different models, so this pins that neither
    drifts into a different flag name or a default-on filter -- the latter would make the shared
    corpus disappear.
    """
    from pathlib import Path

    source = Path(f"services/backend/api/routers/{router}.py").read_text(encoding="utf-8")
    assert "mine: bool = False" in source, f"{router}: filter is missing or not opt-in"
    assert 'alias="X-Engineer-Name"' in source, f"{router}: does not accept the identity header"
