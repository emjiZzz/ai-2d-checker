from bson.errors import InvalidId
from fastapi import Depends, Header, HTTPException, status

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


async def get_or_404(model, id: str, detail: str):
    """
    Shared Document.get() wrapper. Beanie raises InvalidId (not a clean
    404-able None) when `id` isn't a well-formed ObjectId, which previously
    surfaced as an unhandled 500 on every router that took a raw path-param
    id straight into `Model.get(id)`. Use this instead of calling
    `Model.get(id)` directly in route handlers.
    """
    try:
        doc = await model.get(id)
    except InvalidId:
        doc = None
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return doc

async def get_current_user(x_session_token: str = Header(..., alias="X-Session-Token", description="Active session token")) -> "UserAccountDocument":
    from ..core.auth import verify_session_token
    from ..domain.models.user_account import UserAccountDocument
    from ..logger import logger, correlation_id_var
    try:
        payload = verify_session_token(x_session_token)
        username = payload.get("username")
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

