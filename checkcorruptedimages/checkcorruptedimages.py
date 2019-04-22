#!/usr/bin/env python3

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from subprocess import Popen, PIPE

from typing import Any, List, Tuple

from pathlib import Path


def check_image_with_imagemagick(
    file_path: Path
        ) -> Tuple[int, bytes, bytes]:
    """
    Check if image is corrupted with identify function of ImageMagick.
    :param file_path: Path: Image path.

    """

    proc = Popen(
        ["identify", "-verbose", file_path],
        stdout=PIPE,
        stderr=PIPE
        )
    out, err = proc.communicate()
    exitcode = proc.returncode
    return exitcode, out, err


def is_image_corrupted(
    file_path: Path
        ) -> Tuple[Path, bool]:
    """
    Determine if an image is corrupted based on the
        output of check_image_with_imagemagick.
    :param file_path: Path: Image path.

    """

    exitcode, output, error = check_image_with_imagemagick(file_path)

    corrupted = False

    if exitcode != 0 or error != b"":
        corrupted = True
    else:
        corrupted = False

    return file_path, corrupted


def get_files_to_check(
    folder_to_check: Path, file_extensions_list: List[str]
        ) -> List[Path]:
    """
    Get list of file Paths to check.
    :param folder_to_check: Path: Folder to check for corrupted images.
    :param file_extensions_list: List[str]: List of image extensions to check.

    """

    return [
        file for file in list(
            folder_to_check.iterdir()
            ) if file.suffix.lstrip(".") in file_extensions_list
        ]


def check_images_on_pool(
    list_of_files_to_check: List[Path],
    max_workers: int
        ) -> Any:
    """
    Check images concurrently using concurrent.futures.ProcessPoolExecutor.

    :param list_of_files_to_check: List[Path]: List of images to check.
    :param max_workers: int: Max workers to use concurrently.

    """

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return executor.map(
            is_image_corrupted,
            list_of_files_to_check,
            timeout=60
            )


def get_corrupted_images(
    folder_to_check: Path,
    file_extensions_list: List[str],
    max_workers=cpu_count()
        ) -> List[Path]:
    """
    Check for corrupted images on a folder.
    :param folder_to_check: Path: Folder to check for corrupted images.
    :param file_extensions_list: List[str]: List of image extensions to check.
    :param max_workers:  (Default value = cpu_count())
        Max workers to use concurrently.

    """

    files_to_check = get_files_to_check(
        folder_to_check=folder_to_check,
        file_extensions_list=file_extensions_list
        )

    checked_image_list = list(
        check_images_on_pool(
            list_of_files_to_check=files_to_check,
            max_workers=max_workers
            )
        )

    # Return corrupted images.
    return [
        x[0] for x in list(
            filter(
                lambda checked_image_list: checked_image_list[1],
                checked_image_list
                )
            )
        ]
