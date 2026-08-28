#!/usr/bin/env python3

from importlib.metadata import version as package_version

from typer.testing import CliRunner

from checkcorruptedimages._cli import app

runner = CliRunner()


class TestCli:
    def test_reports_corrupted_and_exit_code(self, image_folder):
        result = runner.invoke(app, [str(image_folder), "--ext", "jpg"])

        assert result.exit_code == 1
        assert "corrupted.jpg" in result.output
        assert "fake.jpg" in result.output
        assert "ok.jpg" not in result.output

    def test_clean_folder_exits_zero(self, image_folder, tmp_path):
        (tmp_path / "good.jpg").write_bytes(
            (image_folder / "ok.jpg").read_bytes()
            )

        result = runner.invoke(app, [str(tmp_path)])

        assert result.exit_code == 0
        assert "good.jpg" not in result.output

    def test_lenient_tolerates_truncated(self, image_folder, tmp_path):
        (tmp_path / "cut.jpg").write_bytes(
            (image_folder / "corrupted.jpg").read_bytes()
            )

        strict = runner.invoke(app, [str(tmp_path)])
        lenient = runner.invoke(app, [str(tmp_path), "--lenient"])

        assert strict.exit_code == 1
        assert lenient.exit_code == 0

    def test_ext_filter_skips_other_extensions(self, tmp_path):
        (tmp_path / "fake.png").write_bytes(b"not an image")

        result = runner.invoke(app, [str(tmp_path), "--ext", "jpg"])

        assert result.exit_code == 0

    def test_missing_folder_is_usage_error(self, tmp_path):
        result = runner.invoke(app, [str(tmp_path / "nope")])

        assert result.exit_code not in (0, 1)

    def test_verbose_shows_reasons(self, image_folder):
        result = runner.invoke(
            app, [str(image_folder), "--ext", "jpg", "--verbose"]
            )

        assert result.exit_code == 1
        assert "corrupted: True" in result.output
        assert "reason:" in result.output

    def test_version(self):
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert result.output.strip() == package_version(
            "checkcorruptedimages"
            )
