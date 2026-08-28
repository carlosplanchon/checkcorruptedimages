# checkcorruptedimages
[![CI](https://github.com/carlosplanchon/checkcorruptedimages/actions/workflows/ci.yml/badge.svg)](https://github.com/carlosplanchon/checkcorruptedimages/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/checkcorruptedimages.svg)](https://pypi.org/project/checkcorruptedimages/)
[![Python versions](https://img.shields.io/pypi/pyversions/checkcorruptedimages.svg)](https://pypi.org/project/checkcorruptedimages/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/carlosplanchon/checkcorruptedimages)

*Python module to check for corrupted images by fully decoding them with Pillow in crash-isolated worker processes.*

## Installation
### Install with uv
```
uv add checkcorruptedimages
```
### Install as a CLI tool
```
uv tool install checkcorruptedimages
```
### Install with pip
```
pip install -U checkcorruptedimages
```
No system dependencies: Pillow is installed automatically.

### HEIC/HEIF support
```
pip install -U "checkcorruptedimages[heif]"
```
Installs pillow-heif; the decoder workers register it automatically, so `.heic`/`.heif` files can be checked (e.g. `--ext heic` on the CLI).

## Command line
```
checkcorruptedimages ~/Pictures
checkcorruptedimages ~/Pictures --ext jpg --ext png --lenient --timeout 120 -v
```
Prints one corrupted path per line (a summary goes to stderr) and exits with code 1 if any corrupted image was found. See `checkcorruptedimages --help` for all options. With uv you can try it without installing:
```
uvx checkcorruptedimages ~/Pictures
```

## Usage
```
In [1]: import checkcorruptedimages

In [2]: from pathlib import Path

In [3]: m = checkcorruptedimages.CheckCorruptedImages(verbose=True)

In [4]: m.get_corrupted_images(
    folder_to_check=Path("/home/user/Pictures"),
    file_extensions_list=["jpg"]
    )

Path: /home/user/Pictures/notcorruptedimage.jpg, corrupted: False
Path: /home/user/Pictures/corruptedimage.jpg, corrupted: True, reason: OSError: image file is truncated (14 bytes not processed)
Out[4]: [PosixPath('/home/user/Pictures/corruptedimage.jpg')]
```

To also get the reason for each file, use `get_check_results`, which returns `ImageCheckResult(file_path, corrupted, reason)` records:

```
In [5]: m.get_check_results(
    folder_to_check=Path("/home/user/Pictures"),
    file_extensions_list=["jpg"]
    )
```

For many separate calls, keep the decoder workers alive with a session:

```
In [6]: with m.session() as s:
   ...:     s.is_image_corrupted(Path("/home/user/Pictures/a.jpg"))
   ...:     s.check_files([Path("/home/user/Pictures/b.jpg")])
```

## Behavior
- Every image is fully decoded with Pillow inside a pool of persistent worker subprocesses. A decoder crash or hang only kills a worker: the image is reported as corrupted (reason `decoder crashed` or `timeout`), the worker is respawned and the batch continues.
- The folder is scanned recursively and file extensions are matched case-insensitively.
- With `regard_warnings=True` (default), truncated files that would still partially decode and Pillow warnings (e.g. decompression bombs over `MAX_IMAGE_PIXELS`) count as corruption; API-deprecation warnings are never escalated. With `regard_warnings=False`, only files Pillow cannot decode at all are reported.
- Each image check is limited to `timeout` seconds (default: 60). Use `timeout=None` to disable the limit.
- `max_worker_memory` (bytes; `--max-memory-mb` on the CLI) applies a best-effort memory cap to each decoder worker on POSIX; a decode over the cap is reported as corrupted.
- `on_result=` receives each `ImageCheckResult` as it completes; useful for progress reporting.
- Options can be passed to the constructor or set as attributes: `verbose`, `regard_warnings` and `timeout`.
- The package ships type hints (`py.typed`), checked with mypy in strict mode.
