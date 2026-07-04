"""Model asset upload/list/soft-delete (P0-009).

Every stored file gets a SHA-256 hash and is marked encrypted; raw files are
never served directly — only via the gated download flow with signed URLs.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.model import ModelAsset
from app.schemas.common import ok
from app.services import audit_service
from app.services.storage_service import store

router = APIRouter(tags=["assets"])

_ALLOWED_ASSET = {"face", "body", "expression", "pose", "reference", "ng"}
_ALLOWED_USAGE = {"training", "reference", "review_only", "prohibited"}


@router.post("/models/{model_id}/assets")
async def upload_asset(
    model_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.ASSET_UPLOAD))],
    file: Annotated[UploadFile, File()],
    asset_type: Annotated[str, Form()],
    usage_type: Annotated[str, Form()],
    consent_confirmed: Annotated[bool, Form()] = False,
):
    if asset_type not in _ALLOWED_ASSET:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"asset_type が不正です: {asset_type}")
    if usage_type not in _ALLOWED_USAGE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"usage_type が不正です: {usage_type}")
    # Training use requires explicit consent to be recorded at upload time.
    if usage_type == "training" and not consent_confirmed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "学習利用の素材は同意確認が必要です。")

    data = await file.read()
    file_path, file_hash = store(data, key=f"models/{model_id}/{file.filename}", encrypt=True)
    asset = ModelAsset(
        model_id=model_id,
        asset_type=asset_type,
        file_path=file_path,
        original_filename=file.filename,
        file_hash=file_hash,
        usage_type=usage_type,
        consent_confirmed=consent_confirmed,
        is_encrypted=True,
        uploaded_by=user.id,
    )
    db.add(asset)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create", target_type="model",
                         target_id=model_id, after={"asset_id": str(asset.id), "hash": file_hash})
    db.commit()
    return ok({"id": str(asset.id), "file_hash": file_hash, "file_path": file_path})


@router.get("/models/{model_id}/assets")
def list_assets(
    model_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
):
    rows = db.scalars(
        select(ModelAsset).where(ModelAsset.model_id == model_id, ModelAsset.deleted_at.is_(None))
    ).all()
    return ok([{"id": str(a.id), "asset_type": a.asset_type, "usage_type": a.usage_type,
                "original_filename": a.original_filename, "consent_confirmed": a.consent_confirmed}
               for a in rows])


@router.delete("/assets/{asset_id}")
def delete_asset(
    asset_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.ASSET_UPLOAD))],
):
    a = db.get(ModelAsset, asset_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "資産が見つかりません。")
    a.deleted_at = datetime.now(timezone.utc)  # soft delete by default
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="delete", target_type="model",
                         target_id=str(a.model_id), before={"asset_id": asset_id})
    db.commit()
    return ok({"id": asset_id, "deleted": True})
