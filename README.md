# checkcorruptedimages
*Python module to check for corrupted images using "identify" from ImageMagick as underlying mechanism.*

## Installation
### Install with uv
```
uv add checkcorruptedimages
```
### Install with pip
```
pip install -U checkcorruptedimages
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
Path: /home/user/Pictures/corruptedimage.jpg, corrupted: True
Out[4]: [PosixPath('/home/user/Pictures/corruptedimage.jpg'),
    PosixPath('/home/user/Pictures/corruptedimage2.jpg')
    ]
```

## Behavior
- The folder is scanned recursively and file extensions are matched case-insensitively.
- An image is reported as corrupted when *identify* exits with a non-zero code. By default *-regard-warnings* is passed, so ImageMagick warnings (e.g. a truncated file that still decodes partially) also count as corruption; use `CheckCorruptedImages(regard_warnings=False)` to count only hard decoding errors.
- Each *identify* run is limited to `timeout` seconds per image (default: 60). A run that exceeds it is killed and the image is reported as corrupted. Use `CheckCorruptedImages(timeout=None)` to disable the limit.
- Options can be passed to the constructor or set as attributes: `verbose`, `regard_warnings` and `timeout`.
