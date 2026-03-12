"""
Media upload — store image/video attachments for replies.

Endpoints:
  POST /api/v1/media/upload  — upload a media file (image or video)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media"])

# Ensure attachments directory exists
ATTACHMENTS_DIR = Path(__file__).resolve().parent.parent / "static" / "attachments"


def _ensure_attachment_dir():
    """Create the attachments directory if it doesn't exist."""
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key),
):
    """
    Upload a media file (image or video) for use as a reply attachment.

    The file is saved to static/attachments/ and the path is returned.
    This path can then be set in a persona's `attachment_path` field.

    Returns: {"filename": "...", "path": "static/attachments/..."}
    """
    _ensure_attachment_dir()

    if not file.filename:
        raise HTTPException(400, "File must have a name")

    # Validate file extension
    allowed_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".webm"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_exts:
        raise HTTPException(
            400,
            f"File type {suffix} not allowed. Supported: {', '.join(allowed_exts)}"
        )

    # Save file
    file_path = ATTACHMENTS_DIR / file.filename
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        logger.info(f"Uploaded media: {file.filename} ({len(contents)} bytes)")
        return {
            "filename": file.filename,
            "path": f"static/attachments/{file.filename}",
            "size": len(contents),
        }
    except Exception as e:
        logger.error(f"Failed to save media file {file.filename}: {e}")
        raise HTTPException(500, f"Failed to save file: {e}")
