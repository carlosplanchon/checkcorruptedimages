#!/usr/bin/env python3

import warnings

import pytest
from PIL import ImageFile

from checkcorruptedimages import _worker

STRICT_EXPECTED = {
    "ok.jpg": "ok",
    "UPPER.JPG": "ok",
    "corrupted.jpg": "corrupted",
    "sub/corrupted2.jpg": "corrupted",
    "warn.jpg": "ok",
    "fake.jpg": "corrupted",
    "bomb.jpg": "corrupted",
}

LENIENT_EXPECTED = {
    "ok.jpg": "ok",
    "UPPER.JPG": "ok",
    "corrupted.jpg": "ok",
    "sub/corrupted2.jpg": "ok",
    "warn.jpg": "ok",
    "fake.jpg": "corrupted",
    "bomb.jpg": "ok",
}


@pytest.fixture
def restore_pillow_globals():
    original = ImageFile.LOAD_TRUNCATED_IMAGES
    yield
    ImageFile.LOAD_TRUNCATED_IMAGES = original


class TestCheckOne:
    @pytest.mark.parametrize(
        "name,expected", sorted(STRICT_EXPECTED.items())
        )
    def test_strict(
        self, image_folder, restore_pillow_globals, name, expected
            ):
        _worker.configure(regard_warnings=True)

        status, reason = _worker.check_one(
            path=str(image_folder / name), regard_warnings=True
            )

        assert status == expected
        if expected == "corrupted":
            assert reason
            assert len(reason) <= _worker.MAX_REASON_LENGTH
        else:
            assert reason is None

    @pytest.mark.parametrize(
        "name,expected", sorted(LENIENT_EXPECTED.items())
        )
    def test_lenient(
        self, image_folder, restore_pillow_globals, name, expected
            ):
        _worker.configure(regard_warnings=False)

        status, reason = _worker.check_one(
            path=str(image_folder / name), regard_warnings=False
            )

        assert status == expected
        if expected == "ok":
            assert reason is None

    def test_strict_ignores_deprecation_warnings(
        self, image_folder, restore_pillow_globals, monkeypatch
            ):
        original_open = _worker.Image.open

        def deprecated_open(path):
            warnings.warn("old API", DeprecationWarning, stacklevel=2)
            return original_open(path)

        monkeypatch.setattr(_worker.Image, "open", deprecated_open)
        _worker.configure(regard_warnings=True)

        status, reason = _worker.check_one(
            path=str(image_folder / "ok.jpg"), regard_warnings=True
            )

        assert status == "ok"
        assert reason is None

    def test_strict_escalates_user_warnings(
        self, image_folder, restore_pillow_globals, monkeypatch
            ):
        original_open = _worker.Image.open

        def suspicious_open(path):
            warnings.warn(
                "Possibly corrupt EXIF data.", UserWarning, stacklevel=2
                )
            return original_open(path)

        monkeypatch.setattr(_worker.Image, "open", suspicious_open)
        _worker.configure(regard_warnings=True)

        status, reason = _worker.check_one(
            path=str(image_folder / "ok.jpg"), regard_warnings=True
            )

        assert status == "corrupted"
        assert reason is not None and "UserWarning" in reason
