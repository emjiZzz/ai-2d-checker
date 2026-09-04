from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Header, HTTPException, status
from pydantic import ValidationError

from ..core.security import verify_api_token


async def get_auth_token(token: str = Depends(verify_api_token)) -> str:
    """
    Thin wrapper so routers can keep depending on `get_auth_token` while the
    real verification lives in core.security.verify_api_token (Bearer token,
    constant-time compare). Previously this was a no-op stub that returned a
    hardcoded token and never checked the Authorization header — every route
    depending on it was unauthenticated. Do not revert to that.
    """
    return token


def resolve_username(
    x_session_token: str | None,
    x_engineer_name: str | None = None,
) -> str | None:
    """
    Best-effort username extraction from a session token, for attributing
    created/authored records (Room.created_by, AnnotationDocument.author_id).

    Deliberately non-raising: these routes authenticate via the API bearer
    token (get_auth_token); the session token is an *additional* header that
    identifies which local user acted. Callers that require a guaranteed user
    should depend on get_current_user instead, which validates revocation and
    account status and 401s.

    ## The engineer-name fallback, and what it is NOT

    A prototype build has no login — `App.tsx` renders the workspace directly and never calls
    `initializeAuth`, so `X-Session-Token` is absent and this returned `None` for every request.
    That is why every room created by a tester carries `created_by = None`, and why the
    `?mine=true` owner filter had nothing to filter on.

    `X-Engineer-Name` carries the name chosen in `EngineerPromptModal` so those records can be
    attributed and separated per tester.

    **It is NOT authentication and must never be treated as such.** The name is picked from a
    21-entry dropdown with no password, every installed client holds the same API bearer token,
    and this header is set by the client. Anyone can send any name. It buys **separation**
    — "your workspace lists your work" — not confidentiality, and any endpoint that fetches by id
    still serves any record to any caller.

    The verified session token is therefore tried FIRST and always wins. The fallback applies only
    where there is no session at all, which is exactly the prototype case. Do not use this to gate
    anything that matters; for that, depend on `get_current_user`.
    """
    if x_session_token:
        try:
            from ..core.auth import verify_session_token
            username = verify_session_token(x_session_token).get("username") or None
            if username:
                return username
        except Exception:
            pass

    # Unverified, prototype-only. Bounded and stripped so a malformed header cannot become a
    # 10 KB `created_by` or an empty-string owner that matches nothing.
    #
    # `isinstance` rather than a truthiness check, because this is not always reached through
    # FastAPI. Router functions in this codebase are also called DIRECTLY from tests, and then the
    # parameter still holds the unresolved `Header(...)` default object -- which is truthy and has
    # no `.strip`. `test_drawings_router_error_handling` caught exactly that: an AttributeError
    # inside the identity lookup surfaced as a 500 from the upload route, turning a caller's 400
    # into an internal error. The session-token branch above only escaped it by accident, being
    # wrapped in a try/except.
    if isinstance(x_engineer_name, str):
        candidate = x_engineer_name.strip()[:64]
        if candidate:
            return candidate

    return None


async def get_or_404(model, id: str, detail: str, projection: dict | None = None):
    """
    Shared Document.get() wrapper. A malformed id must be a clean 404, not an
    unhandled 500. Use this instead of calling `Model.get(id)` directly in
    route handlers.

    **Catch both exception types, and do not "tidy" either away.** Which one
    fires depends on the Beanie version, and this guard has already gone inert
    once because of that:

    - Older Beanie called into bson directly and raised `bson.errors.InvalidId`.
    - Beanie 2.x (2.1.0 here) validates the id through a Pydantic `TypeAdapter`
      first (`documents.py::get` -> `parse_object_as`), so it raises
      `pydantic.ValidationError` and **never reaches the bson path at all**.

    So on this version the original `except InvalidId` caught an exception that
    could no longer occur, and every one of the ~24 call sites — annotations,
    audits, drawings — returned 500 for any non-ObjectId path param. It surfaced
    as a supervisor clicking Approve on a client-side canvas marker
    (`phys_chk_restored_1_1786329084013`) and getting INTERNAL_SERVER_ERROR
    instead of "not found".

    The lesson generalises past the version bump: **a guard clause naming a
    concrete exception type is a dependency on that library's internals**, and
    nothing fails when the library stops raising it — the code keeps compiling,
    the tests keep passing, and the guard silently stops guarding.

    `InvalidId` is live again, so the branch above is not merely historical:
    the `projection` path below goes through bson's `ObjectId` directly rather
    than through Beanie's `TypeAdapter`, so a malformed id raises `InvalidId`
    and never reaches the pydantic one. The two branches now each have exactly
    one live caller. Keep both.

    `projection` fetches through the raw collection instead of `Document.get()`,
    for the case where one field dominates the document's transfer cost — see
    `infrastructure/storage/room_results_cache.py` for the measurements. It is a
    mongo projection dict (`{"field": 0}` to exclude). The result is still
    validated into `model`, so callers get the same type either way; a field
    excluded here must therefore be `None`-able on the model.
    """
    try:
        if projection is None:
            doc = await model.get(id)
        else:
            raw = await model.get_pymongo_collection().find_one(
                {"_id": ObjectId(id)}, projection=projection
            )
            doc = model.model_validate(raw) if raw else None
    except (InvalidId, ValidationError):
        doc = None
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return doc

async def get_current_user(x_session_token: str = Header(..., alias="X-Session-Token", description="Active session token")) -> "UserAccountDocument":
    from ..core.auth import verify_session_token
    from ..domain.models.user_account import UserAccountDocument
    from ..domain.models.user_session import UserSessionDocument
    from ..logger import logger, correlation_id_var
    try:
        payload = verify_session_token(x_session_token)
        username = payload.get("username")

        # A signature-valid, non-expired token can still have been explicitly
        # revoked (logout, or an admin-initiated force-logout) — UserSessionDocument
        # is the source of truth for that, HMAC validity alone only proves the
        # token was legitimately issued at some point, not that it's still live.
        session = await UserSessionDocument.find_one(UserSessionDocument.token == x_session_token)
        if not session or not session.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked. Please log in again."
            )

        user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
        if not user or not user.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated or disabled."
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        corr_id = correlation_id_var.get()
        logger.warning(f"[{corr_id}] Session token validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired user session."
        )

def require_role(allowed_role: str):
    async def dependency(current_user: "UserAccountDocument" = Depends(get_current_user)) -> "UserAccountDocument":
        from fastapi import HTTPException, status
        if current_user.role != allowed_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access Denied: Insufficient workspace permissions."
            )
        return current_user
    return dependency

