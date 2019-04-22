# checkcorruptedimages
*Python3 module to check for corrupted images using "identify" from ImageMagick as underlying mechanism.*

## Installation
### Install with pip
```
pip3 install -U checkcorruptedimages
```

## Usage
```
In [1]: import checkcorruptedimages

In [2]: from pathlib import Path

In [3]: checkcorruptedimages.get_corrupted_images(
    folder_to_check=Path("/home/user/Pictures"),
    file_extensions_list=["jpg"]
    )

Out[3]: [PosixPath('/home/user/Pictures/corruptedimage.jpg'),
    PosixPath('/home/user/Pictures/corruptedimage2.jpg'
    ]
```
