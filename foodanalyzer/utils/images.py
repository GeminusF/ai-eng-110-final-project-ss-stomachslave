"""Image validation and safe upload helpers."""

from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4


class ImageValidationError(ValueError):
    pass


def detect_image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ImageValidationError("Only PNG and JPEG images are supported")


def validate_image_path(path: str | Path, max_bytes: int) -> Path:
    image_path = Path(path)
    if not image_path.is_file():
        raise ImageValidationError(f"Image not found: {image_path}")
    if image_path.stat().st_size > max_bytes:
        raise ImageValidationError("Image is larger than the configured limit")
    with image_path.open("rb") as f:
        detect_image_type(f.read(16))
    return image_path


def save_upload_bytes(data: bytes, original_name: str, upload_dir: Path, max_bytes: int) -> Path:
    if not data:
        raise ImageValidationError("Uploaded file is empty")
    if len(data) > max_bytes:
        raise ImageValidationError("Image is larger than the configured limit")
    suffix = detect_image_type(data)
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_stem = Path(original_name).stem
    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", original_stem).strip("_")
    if safe_stem:
        filename = f"{uuid4().hex}_{safe_stem}{suffix}"
    else:
        filename = f"{uuid4().hex}{suffix}"
    safe_path = (upload_dir / filename).resolve()
    root = upload_dir.resolve()
    if not str(safe_path).startswith(str(root)):
        raise ImageValidationError(f"Unsafe upload path for {original_name!r}")
    safe_path.write_bytes(data)
    return safe_path