#!/usr/bin/env python3

import importlib.util
import sys
from importlib.metadata import version as package_version

import pytest
from PIL import Image

import checkcorruptedimages
from checkcorruptedimages import CheckCorruptedImages, ImageCheckResult
from checkcorruptedimages._result import REASON_CRASHED


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

    def test_decompression_bomb_flagged_by_default(self, image_folder):
        m = CheckCorruptedImages()

        _, corrupted = m.is_image_corrupted(image_folder / "bomb.jpg")

        assert corrupted is True

    def test_trailing_garbage_not_flagged(self, image_folder):
        # Semantic change vs 0.x: Pillow does not surface libjpeg's
        # C-level warnings, so recoverable stream damage passes.
        for regard_warnings in (True, False):
            m = CheckCorruptedImages(regard_warnings=regard_warnings)

            _, corrupted = m.is_image_corrupted(image_folder / "warn.jpg")

            assert corrupted is False

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
            "bomb.jpg", "corrupted.jpg", "corrupted2.jpg", "fake.jpg"
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


CRASH_WORKER_SOURCE = """\
import json
import os
import sys

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if "CRASHME" in request["path"]:
        os._exit(1)
    print(json.dumps({"status": "ok", "reason": None}), flush=True)
"""


class TestCheckResults:
    def test_get_check_results_reports_reasons(self, image_folder):
        m = CheckCorruptedImages()

        results = m.get_check_results(
            folder_to_check=image_folder,
            file_extensions_list=["jpg"]
            )

        by_name = {result.file_path.name: result for result in results}
        assert isinstance(by_name["ok.jpg"], ImageCheckResult)
        assert by_name["ok.jpg"].corrupted is False
        assert by_name["ok.jpg"].reason is None
        assert by_name["fake.jpg"].corrupted is True
        assert by_name["fake.jpg"].reason

    def test_verbose_includes_reason(self, image_folder, capsys):
        m = CheckCorruptedImages(verbose=True)

        m.is_image_corrupted(image_folder / "fake.jpg")

        out = capsys.readouterr().out
        assert "fake.jpg" in out
        assert "corrupted: True" in out
        assert "reason:" in out

    def test_check_images_on_pool_keeps_tuple_shape(self, image_folder):
        m = CheckCorruptedImages()
        files = [image_folder / "ok.jpg", image_folder / "fake.jpg"]

        checked = list(m.check_images_on_pool(files, max_workers=2))

        assert checked == [
            (image_folder / "ok.jpg", False),
            (image_folder / "fake.jpg", True),
            ]

    def test_worker_crash_through_public_api(self, tmp_path):
        (tmp_path / "good.jpg").write_bytes(b"x")
        crasher = tmp_path / "CRASHME.jpg"
        crasher.write_bytes(b"x")
        m = CheckCorruptedImages(
            _worker_command=[sys.executable, "-c", CRASH_WORKER_SOURCE]
            )

        corrupted = m.get_corrupted_images(
            folder_to_check=tmp_path, file_extensions_list=["jpg"]
            )
        results = m.get_check_results(
            folder_to_check=tmp_path, file_extensions_list=["jpg"]
            )

        assert corrupted == [crasher]
        by_name = {result.file_path.name: result for result in results}
        assert by_name["CRASHME.jpg"].reason == REASON_CRASHED


PID_WORKER_SOURCE = """\
import json
import os
import sys

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    json.loads(line)
    print(
        json.dumps({"status": "corrupted", "reason": str(os.getpid())}),
        flush=True
        )
"""


class TestSession:
    def test_session_reuses_workers(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"x")
        (tmp_path / "b.jpg").write_bytes(b"x")
        m = CheckCorruptedImages(
            _worker_command=[sys.executable, "-c", PID_WORKER_SOURCE]
            )

        with m.session(max_workers=1) as session:
            first = session.check_files([tmp_path / "a.jpg"])[0].reason
            second = session.check_files([tmp_path / "b.jpg"])[0].reason

        assert first == second

    def test_session_checks_real_images(self, image_folder):
        m = CheckCorruptedImages()

        with m.session(max_workers=1) as session:
            ok = session.is_image_corrupted(image_folder / "ok.jpg")
            fake = session.is_image_corrupted(image_folder / "fake.jpg")

        assert ok == (image_folder / "ok.jpg", False)
        assert fake == (image_folder / "fake.jpg", True)

    def test_closed_session_raises(self, image_folder):
        m = CheckCorruptedImages()
        session = m.session(max_workers=1)
        session.close()

        with pytest.raises(RuntimeError):
            session.check_files([image_folder / "ok.jpg"])


@pytest.mark.skipif(
    importlib.util.find_spec("pillow_heif") is None,
    reason="pillow-heif is not installed"
    )
class TestHeif:
    def test_valid_and_truncated_heic(self, tmp_path):
        from pillow_heif import register_heif_opener
        register_heif_opener()

        Image.radial_gradient("L").convert("RGB").save(
            tmp_path / "photo.heic", quality=80
            )
        data = (tmp_path / "photo.heic").read_bytes()
        (tmp_path / "cut.heic").write_bytes(data[:len(data) // 2])

        m = CheckCorruptedImages()

        corrupted = m.get_corrupted_images(
            folder_to_check=tmp_path, file_extensions_list=["heic"]
            )

        assert corrupted == [tmp_path / "cut.heic"]


class TestVersion:
    def test_dunder_version(self):
        assert checkcorruptedimages.__version__ == package_version(
            "checkcorruptedimages"
            )


class TestOnResult:
    def test_streams_results_and_composes_with_verbose(
        self, image_folder, capsys
            ):
        m = CheckCorruptedImages(verbose=True)
        seen = []

        results = m.get_check_results(
            folder_to_check=image_folder,
            file_extensions_list=["jpg"],
            on_result=seen.append
            )

        assert sorted(r.file_path for r in seen) == sorted(
            r.file_path for r in results
            )
        assert "corrupted:" in capsys.readouterr().out


class TestMemoryLimit:
    def test_worker_command_includes_flag(self):
        m = CheckCorruptedImages(max_worker_memory=123456789)

        worker_command = m._build_worker_command()

        assert "--max-memory" in worker_command
        assert "123456789" in worker_command

    @pytest.mark.skipif(
        sys.platform != "linux",
        reason="RLIMIT_AS is only reliably enforced on Linux"
        )
    def test_memory_limit_flags_hungry_decode(self, image_folder):
        m = CheckCorruptedImages(
            regard_warnings=False,
            max_worker_memory=350 * 1024 * 1024
            )

        _, corrupted = m.is_image_corrupted(image_folder / "bomb.jpg")

        assert corrupted is True
