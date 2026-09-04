from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from ...core.auth import verify_password, create_session_token
from ...domain.models.user_account import UserAccountDocument
from ...domain.models.user_session import UserSessionDocument
from ...infrastructure.database.connection import db_manager
from ...infrastructure.storage.path_resolver import get_storage_root
from ...logger import logger
from ..dependencies import get_auth_token, require_role, get_current_user
from ..schemas import (
    StandardResponse,
    LoginRequest,
    LoginResponse,
    UserAccountResponse,
    CreateUserRequest,
    UpdateUserRequest,
)

router = APIRouter()


@router.post(
    "/auth/login",
    response_model=StandardResponse[LoginResponse],
    summary="Login user and issue session token"
)
async def login_user(request: LoginRequest):
    if not db_manager.is_connected:
        return StandardResponse(
            success=False,
            error={
                "code": "DATABASE_OFFLINE",
                "message": "Local MongoDB database is offline. Please start the database service using 'start-mongo.ps1' or contact the administrator."
            }
        )

    user = await UserAccountDocument.find_one(UserAccountDocument.username == request.username)
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )
        
    # Generate token
    token, expires_at = create_session_token({
        "username": user.username,
        "role": user.role
    })
    
    # Save session
    session = UserSessionDocument(
        token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
        expires_at=expires_at
    )
    await session.save()
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await user.save()
    
    return StandardResponse(
        success=True,
        data=LoginResponse(
            session_token=token,
            username=user.username,
            role=user.role
        )
    )


@router.post(
    "/auth/logout",
    response_model=StandardResponse[dict],
    summary="Revoke the current session token"
)
async def logout_user(x_session_token: str = Header(..., alias="X-Session-Token")):
    """
    Marks the presented session as inactive. This is deliberately independent of
    get_current_user (no full HMAC/expiry gate) — an already-expired or otherwise
    invalid token should still be able to be logged out client-side without the
    server 401ing the logout request itself; lookup is by the stored token value.
    Idempotent: logging out an already-inactive or unknown session still succeeds.
    """
    session = await UserSessionDocument.find_one(UserSessionDocument.token == x_session_token)
    if session and session.active:
        session.active = False
        await session.save()

    return StandardResponse(success=True, data={"message": "Logged out."})


@router.get(
    "/auth/me",
    response_model=StandardResponse[UserAccountResponse],
    summary="Get profile of currently logged-in user"
)
async def get_my_profile(current_user: UserAccountDocument = Depends(get_current_user)):
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(current_user.id),
            username=current_user.username,
            role=current_user.role,
            active=current_user.active,
            created_at=current_user.created_at,
            permissions=current_user.permissions
        )
    )


@router.get(
    "/admin/users",
    response_model=StandardResponse[list[UserAccountResponse]],
    summary="List all registered enterprise accounts",
    dependencies=[Depends(require_role("admin"))]
)
async def list_enterprise_users():
    users = await UserAccountDocument.find_all().to_list()
    res = [
        UserAccountResponse(
            id=str(u.id),
            username=u.username,
            role=u.role,
            active=u.active,
            created_at=u.created_at,
            permissions=u.permissions
        )
        for u in users
    ]
    return StandardResponse(success=True, data=res)


@router.post(
    "/admin/users",
    response_model=StandardResponse[UserAccountResponse],
    summary="Register a new enterprise account",
    dependencies=[Depends(require_role("admin"))]
)
async def create_enterprise_user(request: CreateUserRequest):
    # Check duplicate
    existing = await UserAccountDocument.find_one(UserAccountDocument.username == request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered."
        )
        
    from ...core.auth import get_password_hash
    hashed = get_password_hash(request.password)
    
    user = UserAccountDocument(
        username=request.username,
        hashed_password=hashed,
        role=request.role,
        permissions=request.permissions if request.permissions is not None else (["all"] if request.role == "admin" else ["audit"]),
        active=True
    )
    await user.save()
    
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
            permissions=user.permissions
        )
    )


@router.get(
    "/admin/users/{username}",
    response_model=StandardResponse[UserAccountResponse],
    summary="Get user account details",
    dependencies=[Depends(require_role("admin"))]
)
async def get_enterprise_user(username: str):
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )
        
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
            permissions=user.permissions
        )
    )


@router.delete(
    "/admin/users/{username}",
    response_model=StandardResponse[dict],
    summary="Deactivate or delete an enterprise account",
    dependencies=[Depends(require_role("admin"))]
)
async def delete_enterprise_user(username: str):
    if username == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default administrator account."
        )
        
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )
        
    await user.delete()
    return StandardResponse(success=True, data={"message": f"Successfully deleted user: {username}"})


@router.patch(
    "/admin/users/{username}",
    response_model=StandardResponse[UserAccountResponse],
    summary="Update an enterprise account's parameters or reset password",
    dependencies=[Depends(require_role("admin"))]
)
async def update_enterprise_user(username: str, request: UpdateUserRequest):
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )
        
    if username == "admin":
        if request.active is not None and request.active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the default administrator account."
            )
            
    if request.active is not None:
        user.active = request.active
    if request.role is not None:
        user.role = request.role
    if request.permissions is not None:
        user.permissions = request.permissions
    if request.password is not None:
        from ...core.auth import get_password_hash
        user.hashed_password = get_password_hash(request.password)
        
    await user.save()
    
    return StandardResponse(
        success=True,
        data=UserAccountResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
            permissions=user.permissions
        )
    )


@router.post(
    "/admin/users/{username}/revoke-sessions",
    response_model=StandardResponse[dict],
    summary="Force-logout a user by revoking all of their active sessions",
    dependencies=[Depends(require_role("admin"))]
)
async def revoke_user_sessions(username: str):
    """
    Admin-initiated force-logout: deactivates every currently-active
    UserSessionDocument for this username. The user's existing session
    token(s) will be rejected by get_current_user on their next request,
    regardless of remaining HMAC/expiry validity.
    """
    user = await UserAccountDocument.find_one(UserAccountDocument.username == username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )

    active_sessions = await UserSessionDocument.find(
        UserSessionDocument.username == username,
        UserSessionDocument.active == True  # noqa: E712
    ).to_list()

    for session in active_sessions:
        session.active = False
        await session.save()

    return StandardResponse(
        success=True,
        data={"message": f"Revoked {len(active_sessions)} active session(s) for '{username}'."}
    )


class CustomRule(BaseModel):
    category: str
    severity: str
    rule_type: str  # "layer_check", "text_match", "dimension_range"
    parameter: str
    description: str
    recommendation: str


@router.get(
    "/admin/custom-rules",
    response_model=StandardResponse[list[CustomRule]],
    summary="Get custom administrative compliance rules",
    dependencies=[Depends(get_auth_token)]
)
async def get_custom_rules():
    """
    Retrieves the active list of user-defined compliance constraints.
    """
    import json
    config_dir = get_storage_root() / "config"
    config_file = config_dir / "custom_rules.json"
    if not config_file.exists():
        return StandardResponse(success=True, data=[])
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        return StandardResponse(success=True, data=[CustomRule(**item) for item in data])
    except Exception:
        return StandardResponse(success=True, data=[])


@router.post(
    "/admin/custom-rules",
    response_model=StandardResponse[dict],
    summary="Add a custom compliance rule",
    dependencies=[Depends(get_auth_token)]
)
async def add_custom_rule(rule: CustomRule):
    """
    Appends a new custom rule definition to active persistence.
    """
    import json
    config_dir = get_storage_root() / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "custom_rules.json"

    rules = []
    if config_file.exists():
        try:
            rules = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    rules.append(rule.dict())
    config_file.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
    return StandardResponse(success=True, data={"message": "Custom rule added successfully."})
