#!/usr/bin/env python3

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture(scope="session")
def image_folder(tmp_path_factory) -> Path:
    """
    Folder with generated test files covering every detection path:
        a valid image, a valid image with uppercase extension,
        truncated images (one inside a subfolder), an image with
        trailing garbage that Pillow tolerates, a decompression-bomb
        header, a non-image file with image extension and a
        non-image extension file.
    """

    folder = tmp_path_factory.mktemp("images")
    (folder / "sub").mkdir()

    ok_path = folder / "ok.jpg"
    Image.radial_gradient("L").convert("RGB").save(ok_path, quality=90)

    data = ok_path.read_bytes()
    assert data[-2:] == b"\xff\xd9", "generated JPEG has no EOI marker"

    start_of_scan = data.index(b"\xff\xda")
    assert int(len(data) * 0.4) > start_of_scan, (
        "truncation point must fall inside the entropy-coded data"
        )

    (folder / "UPPER.JPG").write_bytes(data)
    (folder / "corrupted.jpg").write_bytes(data[:int(len(data) * 0.4)])
    (folder / "sub" / "corrupted2.jpg").write_bytes(
        data[:int(len(data) * 0.5)]
        )
    (folder / "warn.jpg").write_bytes(data[:-2] + b"\x00" * 16 + b"\xff\xd9")
    (folder / "fake.jpg").write_bytes(b"this is not an image")
    (folder / "notes.txt").write_text("not an image")

    # 9500x9500 = 90.25 Mpx: above Pillow's MAX_IMAGE_PIXELS warning
    # threshold (~89.5 Mpx) but below the 2x DecompressionBombError
    # threshold, so strict mode flags it and lenient mode decodes it
    # (~270 MB transient allocation in a single worker).
    start_of_frame = data.index(b"\xff\xc0")
    dimension = (9500).to_bytes(2, "big")
    (folder / "bomb.jpg").write_bytes(
        data[:start_of_frame + 5]
        + dimension + dimension
        + data[start_of_frame + 9:]
        )

    return folder
