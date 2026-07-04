"""Signed file access. The ONLY way raw stored bytes leave the system.

Requires a valid HMAC token minted by storage_service.signed_url (short TTL).
There is no unauthenticated/public path to raw image files (docs/06 §1).
"""

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.services.storage_service import read, verify_signed_token

router = APIRouter(tags=["files"])


@router.get("/files")
def get_file(
    uri: str = Query(...),
    exp: int = Query(...),
    sig: str = Query(...),
):
    if not verify_signed_token(uri, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "署名が無効または期限切れです。")
    try:
        data = read(uri)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません。")
    return Response(content=data, media_type="application/octet-stream")
