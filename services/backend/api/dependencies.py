from fastapi import Depends, Header, HTTPException, status

from ..core.security import verify_api_token


def get_auth_token(token: str = Depends(verify_api_token)) -> str:
    """
    Dependency that enforces secure API token validation.
    Returns the validated token.
    """
    return token

async def get_current_user(x_session_token: str = Header(..., alias="X-Session-Token", description="Active session token")) -> "UserAccountDocument":
    from ..core.auth import verify_jwt_token
    from ..domain.models.user_account import UserAccountDocument
    try:
        payload = verify_jwt_token(x_session_token)
        username = payload.get("username")
        user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
        if not user or not user.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated or disabled."
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired user session: {str(e)}"
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

