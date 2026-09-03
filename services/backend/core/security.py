import secrets
from pathlib import Path

from fastapi import Header, HTTPException, status

from ..config import settings
from ..logger import logger

# Secure Config & API Token Management
TOKEN_FILE_NAME = ".api-token"

def _restrict_token_file_permissions(token_file: Path) -> None:
    """Narrow the token file to the owner, and be honest about where that holds.

    This replaces a comment that read *"Restrict permissions on Windows/Unix where possible"* above
    a plain `write_text` — i.e. a claimed control with no implementation, which is exactly the kind
    of line a security audit reads as a verified fact.

    **POSIX:** `0o600` is real — owner read/write, nothing for group or other.

    **Windows, which is the primary platform here:** `chmod` maps only onto the read-only flag and
    does **not** restrict other users; the file inherits its parent ACL. So on Windows this call is
    close to a no-op and the file's protection is the user profile directory, not this line. Doing
    it properly needs an ACL rewrite (`icacls` or pywin32) and is not attempted here rather than
    being faked. The token is AES-GCM encrypted at rest, but see `core/encryption.py` — the key is
    derived from machine and user name, so treat this file as obfuscated, not sealed.
    """
    try:
        token_file.chmod(0o600)
    except OSError as err:
        # Never fatal: a token that cannot be permission-narrowed is still a working token, and
        # failing startup over it would trade an availability outage for a marginal hardening.
        logger.warning(f"Could not restrict permissions on the API token file: {err}")


#: Folder name under the per-user data root that the token is published to.
#:
#: 🔴 **Deliberately NOT the Tauri bundle identifier** (`com.kmti.checker`), which this used to be.
#: That directory is the desktop app's OWN data directory: WebView2 stores its profile there, and
#: the uninstaller deletes it. Publishing the credential inside it meant an uninstall/reinstall
#: cycle removed the token -- and because it was written only at backend startup, nothing put it
#: back. Measured from the backend access log on 2026-08-27: an installed build launched after a
#: reinstall answered `POST /api/v1/rooms` and `GET /api/v1/rooms` with 401 at 05:16, and began
#: succeeding at 05:18 only because a diagnostic command happened to re-run token initialisation.
#:
#: A sibling directory is not touched by the uninstaller and does not collide with the webview's
#: own storage. Kept in step with the Rust side by `tests/test_user_token_dir.py`, which parses
#: `security/mod.rs` rather than trusting this comment.
TOKEN_DIR_NAME = "kmti-2d-checker"

#: The bundle identifier, recorded only so the test above can assert the token directory is NOT
#: it. Never join a path from this.
APP_IDENTIFIER = "com.kmti.checker"


def user_storage_root() -> Path:
    """A per-user storage root an INSTALLED desktop app can find without knowing this repo.

    ## Why the token needs a second home

    `get_storage_root()` resolves to `<repo>/storage`, which is correct for the backend and
    useless to an installed client. The Tauri app looks for `<storage root>/secure/.api-token` by
    walking up from its own executable and from the working directory -- and an app installed to
    `C:\\Program Files\\KMTI Checker\\` has no `storage` anywhere up that tree.

    The result was not a visible error. `GET /health` requires no token and returned 200, so the
    app reported itself **connected** while every authenticated call answered 401: the rooms list
    came back empty and "Create Room" did nothing at all. Reported from the first installed
    prototype build as "I can't create a room and proceed".

    ## Why this is safe to write

    The blob is AES-GCM encrypted under a key derived from machine and user identity (see
    `core/encryption.py` and the Rust `security/encryption.rs`), so a copy is bound to this
    machine and this user -- carrying it to another machine yields ciphertext that will not
    decrypt. Writing it under the user's own local app data is the same trust boundary as
    `<repo>/storage/secure`, not a wider one.

    ⚠ **Local, never roaming.** On Windows this is `%LOCALAPPDATA%`, not `%APPDATA%`, precisely
    because the key is machine-bound: a roaming profile would sync a credential to machines where
    it cannot decrypt, which is all cost and no benefit.
    """
    import os
    import sys

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else Path.home() / ".local" / "share"

    return root / TOKEN_DIR_NAME


def _mirror_token_for_installed_clients(token: str) -> None:
    """Publish the active token where an installed app can read it.

    Written on every startup rather than only when a token is generated: the generate branch runs
    once in the life of a checkout, so an existing install would otherwise never receive a copy.
    Re-encrypting each time is intentional and cheap -- AES-GCM uses a fresh nonce, so the
    ciphertext differs while the plaintext does not.

    Never fatal. A backend that cannot write this still serves every client that can reach
    `<repo>/storage`, and refusing to start over a convenience path would trade an outage for it.
    """
    try:
        secure_dir = user_storage_root() / "secure"
        secure_dir.mkdir(parents=True, exist_ok=True)
        mirrored = secure_dir / TOKEN_FILE_NAME

        from .encryption import encryptor

        mirrored.write_text(encryptor.encrypt(token), encoding="utf-8")
        _restrict_token_file_permissions(mirrored)
        logger.info(f"Published API token for installed clients at: {mirrored}")
    except Exception as err:  # noqa: BLE001 - see docstring; this must not break startup
        logger.warning(f"Could not publish the API token for installed clients: {err}")


def ensure_token_published() -> None:
    """Re-publish the token for installed clients if the file is missing or out of sync.

    Publishing only at startup was not enough. The file can disappear while the backend keeps
    running -- an uninstall of the desktop app took it with the app's data directory before
    `TOKEN_DIR_NAME` moved out of that tree, and a user clearing app data can still do it. A
    crashed server instance or foreign process could also overwrite it with a mismatched credential.
    Once gone or desynchronized, every authenticated request from a desktop client answered 401.

    Called from `/health`, which is the one endpoint that needs no token and which the desktop
    client already polls every few seconds -- so the repair happens before the user notices,
    without adding a scheduler.
    """
    if not settings.API_TOKEN:
        return
    try:
        mirrored = user_storage_root() / "secure" / TOKEN_FILE_NAME
        if mirrored.is_file():
            from .encryption import encryptor

            existing = encryptor.decrypt(mirrored.read_text(encoding="utf-8").strip())
            if existing == settings.API_TOKEN:
                return
    except Exception:  # noqa: BLE001 - an unreadable, corrupt, or mismatched file requires republishing
        pass
    _mirror_token_for_installed_clients(settings.API_TOKEN)


def initialize_local_api_token() -> str:
    """
    Returns the local security authentication token.
    If none is set in env variables, generates a cryptographically secure token
    and writes it to storage/secure/ for Tauri client retrieval.

    Also mirrors it to `user_storage_root()` so a client installed outside this checkout -- which
    cannot find `<repo>/storage` at all -- can authenticate. See `_mirror_token_for_installed_clients`.
    """
    token = settings.API_TOKEN

    from ..infrastructure.storage.path_resolver import get_storage_root

    # Ensure storage/secure folder exists
    secure_dir = get_storage_root() / "secure"
    secure_dir.mkdir(parents=True, exist_ok=True)
    token_file = secure_dir / TOKEN_FILE_NAME

    if not token:
        if token_file.exists():
            try:
                encrypted_content = token_file.read_text(encoding="utf-8").strip()
                from .encryption import encryptor
                token = encryptor.decrypt(encrypted_content)
                logger.info("Loaded and decrypted persisted dynamic API Token from secure local storage.")
            except Exception as e:
                logger.error(f"Failed to read or decrypt persisted token: {str(e)}")

        if not token:
            token = secrets.token_hex(32)
            try:
                from .encryption import encryptor
                encrypted_content = encryptor.encrypt(token)
                token_file.write_text(encrypted_content, encoding="utf-8")
                _restrict_token_file_permissions(token_file)
                logger.info(f"Generated secure encrypted dynamic API Token saved to: {token_file}")
            except Exception as e:
                logger.error(f"Failed to encrypt and persist dynamically generated API Token: {str(e)}")

    # Update config settings with active token
    settings.API_TOKEN = token

    # Publish it where an installed client can find it. After the branches above, so it mirrors
    # the token actually in force -- whether it came from the environment, an existing file, or
    # was generated a moment ago.
    if token:
        _mirror_token_for_installed_clients(token)

    return token

def verify_api_token(authorization: str | None = Header(None, description="API Security Bearer Token")) -> str:
    """
    FastAPI dependency validating requests contain the exact matching localhost token.
    Rejects unauthorized queries with 401.
    """
    if not settings.API_TOKEN:
        # If token was not initialized, initialize it now
        initialize_local_api_token()

    if not authorization:
        logger.warning("Rejected API request: Missing Authorization header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Missing Authorization Header."
        )

    expected_prefix = "Bearer "
    if not authorization.startswith(expected_prefix):
        logger.warning("Rejected API request: Authorization header missing Bearer prefix.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Bearer prefix required."
        )

    provided_token = authorization[len(expected_prefix):].strip()
    if not secrets.compare_digest(provided_token, settings.API_TOKEN or ""):
        logger.warning("Rejected API request: Unauthorized API Token provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Invalid security API Token."
        )

    return provided_token

# Dual-Layer Path Traversal Protection
def validate_sandboxed_path(user_path: str | Path) -> Path:
    """
    Canonical absolute path resolver. Validates path stays bounded inside the storage root directory.
    Blocks all path traversal attempts (../), symlink escapes, and invalid absolute outside boundaries.

    Uses ``get_storage_root()`` (from ``path_resolver``) as the single source of truth for the
    storage root so this guard is always consistent with every other path-building helper in
    the codebase, regardless of the process working directory.
    """
    # Local import prevents circular dependency:
    #   security → path_resolver → config  (safe one-way chain)
    from ..infrastructure.storage.path_resolver import get_storage_root

    storage_root = get_storage_root()
    raw = str(user_path)

    # 1. Reject a NUL byte before pathlib sees it. `Path.resolve()` raises a bare ValueError on
    #    embedded NULs, and that used to escape this function uncaught — surfacing as a 500 from
    #    the error middleware rather than the 400 this guard's contract promises. A rejected path
    #    must look rejected, not look like a server fault.
    if "\x00" in raw:
        logger.error("Path Traversal Attempt Blocked: path contains a NUL byte.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path contains illegal characters."
        )

    # 2. Block traversal *components*, before resolution.
    #    This check used to run after `.resolve()` had already made traversal impossible, and it
    #    tested `".." in str(path)` — a substring. So it caught nothing the resolution had not
    #    already caught, while rejecting legitimate filenames that merely contain two dots, e.g.
    #    `rev..2.dxf`. Checking parts instead means it rejects real traversal early, with a
    #    precise message, and stops rejecting valid names.
    if ".." in Path(raw).parts:
        logger.error(f"Path Traversal Attempt Blocked: Path contains invalid traversal operators: {user_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path contains illegal traversal operators."
        )

    try:
        target_path = Path(raw).resolve()
    except (ValueError, OSError) as err:
        logger.error(f"Path Traversal Attempt Blocked: path could not be resolved: {err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path could not be resolved."
        ) from err

    # 3. Containment check: the canonical path must sit inside the storage root. This is the
    #    load-bearing layer — it defeats symlink escapes and absolute paths, since `.resolve()`
    #    has already followed every link and normalised every segment.
    try:
        target_path.relative_to(storage_root)
    except ValueError:
        logger.error(
            f"Path Traversal Attempt Blocked: Resolved path '{target_path}' "
            f"escapes storage root boundary '{storage_root}'."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access Denied: Path escapes the sandboxed workspace directory."
        )

    return target_path


def sandboxed_path(*parts: str | Path) -> Path:
    """Join `parts` under the storage root and validate the result, in one call.

    Prefer this over ``get_storage_root() / a / b`` at every file-serving site. Two reasons, both
    of which were live defects:

    **1. `/` silently discards the root when the right operand is absolute.**
    ``get_storage_root() / drawing.file_path`` evaluates to ``drawing.file_path`` alone if that
    DB value is ever absolute — the sandbox does not fail, it ceases to exist. Any part that is
    absolute is rejected here rather than honoured.

    **2. Validate-and-discard.** Most existing callers ran ``validate_sandboxed_path(p)`` for its
    exception and then used ``p`` — so the canonical, checked path was computed and thrown away.
    A helper that returns the only path you have no reason to discard removes the opportunity.

    Raises ``HTTPException(400)`` for absolute parts, traversal components, NUL bytes, and any
    join that lands outside the storage root.
    """
    from ..infrastructure.storage.path_resolver import get_storage_root

    candidate = get_storage_root()
    for part in parts:
        if Path(part).is_absolute() or (isinstance(part, str) and part.startswith(("/", "\\"))):
            logger.error(
                f"Path Traversal Attempt Blocked: absolute segment '{part}' "
                f"would discard the storage root."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access Denied: Path segment must be relative to the storage root."
            )
        candidate = candidate / part

    return validate_sandboxed_path(candidate)


# `mask_secret()` was removed 2026-08-11. It masked a secret for logging and had **zero call
# sites** from the day it was written — a repo-wide grep returned only its own definition. It was
# deleted rather than kept because it was not neutral dead code: the 2026-08-11 audit package
# cited it as a verified control ("automatically obfuscates API keys and bearer tokens prior to
# writing diagnostic logs"), which was true of the function and false of the system.
#
# There is nothing to wire it into. No log site in this backend emits a secret *value* — the ones
# that mention keys or tokens log the file path, or the fact that a key is absent. If that ever
# changes, mask at the call site; a four-line helper is cheaper to rewrite than to keep honest.
