from pathlib import Path

import pytest

from foodanalyzer.utils.images import ImageValidationError, save_upload_bytes, validate_image_path


PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000"
    "00907753de0000000c4944415408d76360000000000004000146a13a"
    "020000000049454e44ae426082"
)


def test_validate_image_path_accepts_png(sample_image):
    assert validate_image_path(sample_image, max_bytes=10_000).is_file()


def test_validate_image_path_rejects_non_image(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("not an image")
    with pytest.raises(ImageValidationError):
        validate_image_path(path, max_bytes=10_000)


def test_validate_image_path_rejects_oversize(sample_image):
    with pytest.raises(ImageValidationError):
        validate_image_path(sample_image, max_bytes=1)


def test_save_upload_bytes_generates_safe_png_path(tmp_path):
    saved = save_upload_bytes(PNG_BYTES, "../../bad.png", tmp_path, max_bytes=10_000)
    assert saved.parent == tmp_path.resolve()
    assert saved.suffix == ".png"
    assert saved.read_bytes() == PNG_BYTES