#!/usr/bin/env python3

import shutil

from pathlib import Path

from subprocess import run

import pytest


@pytest.fixture(scope="session")
def image_folder(tmp_path_factory) -> Path:
    """
    Folder with generated test files covering every detection path:
        a valid image, a valid image with uppercase extension,
        truncated images (one inside a subfolder), an image with
        garbage bytes that decodes with warnings, a non-image file
        with image extension and a non-image extension file.
    Skips the requesting tests when ImageMagick is not installed.
    """

    generator = shutil.which("magick") or shutil.which("convert")
    if generator is None or shutil.which("identify") is None:
        pytest.skip("ImageMagick (magick/identify) is not installed.")

    folder = tmp_path_factory.mktemp("images")
    (folder / "sub").mkdir()

    ok_path = folder / "ok.jpg"
    result = run(
        [generator, "-size", "256x256", "plasma:fractal", str(ok_path)],
        capture_output=True
        )
    assert result.returncode == 0, result.stderr

    data = ok_path.read_bytes()
    assert data[-2:] == b"\xff\xd9", "generated JPEG has no EOI marker"

    (folder / "UPPER.JPG").write_bytes(data)
    (folder / "corrupted.jpg").write_bytes(data[:int(len(data) * 0.4)])
    (folder / "sub" / "corrupted2.jpg").write_bytes(
        data[:int(len(data) * 0.5)]
        )
    (folder / "warn.jpg").write_bytes(data[:-2] + b"\x00" * 16 + b"\xff\xd9")
    (folder / "fake.jpg").write_bytes(b"this is not an image")
    (folder / "notes.txt").write_text("not an image")

    return folder
