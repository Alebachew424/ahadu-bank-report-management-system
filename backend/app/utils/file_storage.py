import os
import shutil
from pathlib import Path
from fastapi import UploadFile
import uuid

# Resolve MEDIA_ROOT relative to this file so it works regardless of CWD
_THIS_DIR = Path(__file__).resolve().parent           # app/utils/
_BACKEND_DIR = _THIS_DIR.parent.parent                # backend/
MEDIA_ROOT = _BACKEND_DIR / "media"

def ensure_media_dir():
    MEDIA_ROOT.mkdir(exist_ok=True)

def save_upload_file(upload_file: UploadFile, request_id: int, version: int) -> dict:
    ensure_media_dir()
    # Create a subfolder per request
    request_dir = MEDIA_ROOT / str(request_id)
    request_dir.mkdir(exist_ok=True)

    # Generate unique filename to avoid collisions
    ext = Path(upload_file.filename).suffix
    unique_name = f"v{version}_{uuid.uuid4().hex}{ext}"
    file_path = request_dir / unique_name

    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    # Get file size
    size = file_path.stat().st_size

    return {
        "stored_path": str(file_path.relative_to(MEDIA_ROOT.parent)),  # relative to backend/
        "file_size": size,
        "file_name": upload_file.filename,
        "mime_type": upload_file.content_type or "application/octet-stream",
    }

def delete_file(stored_path: str):
    """stored_path is relative to backend/ (e.g. media/1/v1_abc.pdf)"""
    full_path = _BACKEND_DIR / stored_path
    if full_path.exists():
        full_path.unlink()

def get_file_path(stored_path: str) -> Path:
    """Return the absolute path for a stored_path relative to backend/."""
    return _BACKEND_DIR / stored_path
