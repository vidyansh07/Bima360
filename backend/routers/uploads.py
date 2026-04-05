"""
Uploads router — S3 presigned URL generation for document uploads.
Frontend uploads directly to S3 using the presigned URL (never via FastAPI).
"""
import re
import uuid
from pathlib import PurePosixPath

import boto3
from fastapi import APIRouter, Depends, HTTPException, status

from backend.core.config import settings
from backend.core.dependencies import get_current_agent
from backend.core.responses import ok
from backend.schemas.schemas import PresignedUrlResponse

router = APIRouter(prefix="/uploads", tags=["Uploads"])

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".heic"}
_MAX_FILE_SIZE_MB = 10


def _s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


@router.get("/presign", response_model=dict)
async def get_presigned_url(
    filename: str,
    doc_type: str = "claim_document",
    agent: dict = Depends(get_current_agent),
):
    """
    Generate a presigned S3 PUT URL for direct frontend upload.
    Returns: { url, key, expires_in }
    """
    # Sanitize filename — strip path traversal and restrict to safe chars
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", PurePosixPath(filename).name)
    ext = PurePosixPath(safe_name).suffix.lower()

    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Use: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    object_key = f"uploads/{doc_type}/{uuid.uuid4()}/{safe_name}"

    import asyncio

    presigned_url = await asyncio.to_thread(
        _s3_client().generate_presigned_url,
        "put_object",
        Params={
            "Bucket": settings.AWS_S3_BUCKET,
            "Key": object_key,
            "ContentType": _mime_type(ext),
        },
        ExpiresIn=300,
    )

    return ok(
        PresignedUrlResponse(
            url=presigned_url,
            key=object_key,
            expires_in=300,
        ).model_dump()
    )


def _mime_type(ext: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".pdf": "application/pdf",
        ".heic": "image/heic",
    }.get(ext, "application/octet-stream")
