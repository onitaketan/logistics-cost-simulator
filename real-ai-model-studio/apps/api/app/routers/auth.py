from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    CurrentUserDep,
    create_access_token,
    verify_password,
    verify_totp,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ok
from app.schemas.dto import LoginRequest
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "メールアドレスまたはパスワードが不正です。")
    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "このアカウントは停止されています。")

    settings = get_settings()
    if settings.require_2fa and not user.totp_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "二要素認証の登録が必要です。")
    if not verify_totp(user.totp_secret, body.otp_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ワンタイムコードが不正です。")

    token = create_access_token(str(user.id), user.email, user.role)
    audit_service.record(
        db, user_id=str(user.id), action_type="login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return ok({"access_token": token, "token_type": "bearer", "role": user.role})


@router.post("/logout")
def logout(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    audit_service.record(db, user_id=user.id, action_type="logout")
    db.commit()
    return ok({"logged_out": True})
