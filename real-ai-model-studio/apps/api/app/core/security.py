"""Auth primitives: password hashing, JWT, 2FA, and FastAPI dependencies.

MVP uses self-issued JWT so the system is not blocked on an external IdP. The
token issuance is isolated here so Auth0 / Azure AD / Supabase Auth can be
swapped in later without touching routers.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rbac import Perm, has_permission
from app.db.session import get_db

_ALGO = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _b(raw: str) -> bytes:
    # bcrypt hard-limits input to 72 bytes; truncate deterministically.
    return raw.encode("utf-8")[:72]


class CurrentUser(BaseModel):
    id: str
    email: str
    role: str


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(_b(raw), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_b(raw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_totp(secret: str | None, code: str | None) -> bool:
    if not secret:
        return True  # 2FA not enrolled for this user
    if not code:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def create_access_token(user_id: str, email: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.api_secret_key, algorithm=_ALGO)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, get_settings().api_secret_key, algorithms=[_ALGO])
    except JWTError:
        raise creds_exc
    sub = payload.get("sub")
    if not sub:
        raise creds_exc

    # Re-validate against the live user record. A token is a bearer credential
    # with a lifetime; trusting its embedded role/status would let a suspended
    # user — or one whose role was downgraded — keep full access until expiry.
    # Load the user, reject if missing or not active, and take role from the DB
    # (not the token) so revocations take effect immediately (docs/06 §1).
    from app.models.user import User  # local import avoids a circular import

    user = db.get(User, sub)
    if user is None or user.status != "active":
        raise creds_exc
    return CurrentUser(id=str(user.id), email=user.email, role=user.role)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require(perm: Perm):
    """Dependency factory that enforces an RBAC permission."""

    def _dep(user: CurrentUserDep) -> CurrentUser:
        if not has_permission(user.role, perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{user.role}' lacks permission '{perm}'",
            )
        return user

    return _dep
