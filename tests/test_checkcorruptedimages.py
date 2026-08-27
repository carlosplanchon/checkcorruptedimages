#!/usr/bin/env python3

import pytest

from checkcorruptedimages import CheckCorruptedImages


class TestOptions:
    def test_defaults(self):
        m = CheckCorruptedImages()
        assert m.verbose is False
        assert m.regard_warnings is True
        assert m.timeout == 60

    def test_constructor_options(self):
        m = CheckCorruptedImages(
            verbose=True, regard_warnings=False, timeout=None
            )
        assert m.verbose is True
        assert m.regard_warnings is False
        assert m.timeout is None


class TestGetFilesToCheck:
    def test_recursive_and_case_insensitive(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"x")
        (tmp_path / "B.JPG").write_bytes(b"x")
        (tmp_path / "c.png").write_bytes(b"x")
        (tmp_path / "notes.txt").write_text("x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "d.jpeg").write_bytes(b"x")

        m = CheckCorruptedImages()
        found = m.get_files_to_check(
            folder_to_check=tmp_path,
            file_extensions_list=["jpg", ".JPEG"]
            )

        assert sorted(p.name for p in found) == ["B.JPG", "a.jpg", "d.jpeg"]

    def test_directories_are_ignored(self, tmp_path):
        (tmp_path / "folder.jpg").mkdir()

        m = CheckCorruptedImages()

        assert m.get_files_to_check(
            folder_to_check=tmp_path, file_extensions_list=["jpg"]
            ) == []

    def test_missing_folder_raises(self, tmp_path):
        m = CheckCorruptedImages()

        with pytest.raises(FileNotFoundError):
            m.get_files_to_check(
                folder_to_check=tmp_path / "nope",
                file_extensions_list=["jpg"]
                )


class TestIsImageCorrupted:
    def test_valid_image(self, image_folder):
        m = CheckCorruptedImages()
        path = image_folder / "ok.jpg"

        assert m.is_image_corrupted(path) == (path, False)

    def test_truncated_image(self, image_folder):
        m = CheckCorruptedImages()

        _, corrupted = m.is_image_corrupted(image_folder / "corrupted.jpg")

        assert corrupted is True

    def test_warning_image_flagged_by_default(self, image_folder):
        m = CheckCorruptedImages()

        _, corrupted = m.is_image_corrupted(image_folder / "warn.jpg")

        assert corrupted is True

    def test_valid_image_accepted_without_regard_warnings(self, image_folder):
        m = CheckCorruptedImages(regard_warnings=False)

        _, corrupted = m.is_image_corrupted(image_folder / "ok.jpg")

        assert corrupted is False

    def test_non_image_is_hard_error(self, image_folder):
        m = CheckCorruptedImages(regard_warnings=False)

        _, corrupted = m.is_image_corrupted(image_folder / "fake.jpg")

        assert corrupted is True

    def test_timeout_marks_corrupted(self, image_folder):
        m = CheckCorruptedImages(timeout=0.000001)

        _, corrupted = m.is_image_corrupted(image_folder / "ok.jpg")

        assert corrupted is True

    def test_verbose_prints_status(self, image_folder, capsys):
        m = CheckCorruptedImages()
        m.verbose = True

        m.is_image_corrupted(image_folder / "ok.jpg")

        out = capsys.readouterr().out
        assert "ok.jpg" in out
        assert "corrupted: False" in out


class TestGetCorruptedImages:
    def test_finds_all_corrupted_recursively(self, image_folder):
        m = CheckCorruptedImages()

        corrupted = m.get_corrupted_images(
            folder_to_check=image_folder,
            file_extensions_list=["jpg"]
            )

        assert sorted(p.name for p in corrupted) == [
            "corrupted.jpg", "corrupted2.jpg", "fake.jpg", "warn.jpg"
            ]

    def test_hard_error_mode_flags_subset_of_default(self, image_folder):
        strict = set(
            CheckCorruptedImages().get_corrupted_images(
                folder_to_check=image_folder,
                file_extensions_list=["jpg"]
                )
            )
        lenient = set(
            CheckCorruptedImages(regard_warnings=False).get_corrupted_images(
                folder_to_check=image_folder,
                file_extensions_list=["jpg"]
                )
            )

        assert lenient <= strict
        assert image_folder / "fake.jpg" in lenient
