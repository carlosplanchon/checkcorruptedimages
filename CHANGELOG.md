# Changelog

## [1.0.0] - 2026-08-27

First stable release. The decoding backend moved from ImageMagick to Pillow, removing every system dependency while keeping crash isolation.

### Added
- CLI: `checkcorruptedimages FOLDER` with `--ext`, `--lenient`, `--timeout`, `--workers`, `--verbose`, `--max-memory-mb` and `--version`; exit code 1 when corrupted images are found.
- `get_check_results()` / `check_files()` returning `ImageCheckResult(file_path, corrupted, reason)` records with the corruption reason.
- `session()` / `CheckSession`: keep decoder workers alive across calls.
- `on_result` callback for streaming progress in completion order.
- `max_worker_memory` option: best-effort memory belt (`RLIMIT_AS`) for the decoder workers on POSIX.
- Optional HEIC/HEIF support: `checkcorruptedimages[heif]` (pillow-heif), registered automatically by the workers.
- Type hints shipped (`py.typed`), checked with mypy in strict mode.
- Per-image timeout that kills a hung decoder and reports the image as corrupted.
- Recursive, case-insensitive folder scanning.
- Test suite (pytest), CI matrix (Linux 3.10-3.14, Windows, macOS), lint job (ruff + mypy) and trusted publishing to PyPI.

### Changed
- Images are fully decoded with Pillow inside persistent sacrificial worker subprocesses: a decoder crash or hang only kills a worker; the image is reported as corrupted (reason `decoder crashed` / `timeout`) and the batch continues.
- `regard_warnings=True` (default) now maps to Pillow strictness: truncated files that would still partially decode and Pillow warnings (e.g. decompression bombs) count as corruption; API-deprecation warnings are never escalated.
- Packaging moved to `pyproject.toml` with the `uv_build` backend; ImageMagick is no longer used nor required.

### Removed
- `check_image_with_imagemagick()`. `check_images_on_pool()` stays as a compatibility wrapper.
- Detection of libjpeg's recoverable C-level warnings (e.g. stray bytes in the stream): Pillow does not surface them, so those files are no longer flagged.

## [0.3]

Last ImageMagick-based release, published on PyPI.
