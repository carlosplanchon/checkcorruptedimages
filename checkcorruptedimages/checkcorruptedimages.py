#!/usr/bin/env python3

from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from subprocess import Popen, PIPE, TimeoutExpired

from pathlib import Path


class CheckCorruptedImages:
    """
    Python class to check for corrupted images using identify function
        of ImageMagick concurrently.
    """
    def __init__(
        self,
        verbose: bool = False,
        regard_warnings: bool = True,
        timeout: float | None = 60
            ):
        """
        :param verbose: bool: Print the status of each checked image.
        :param regard_warnings: bool: Treat ImageMagick warnings as
            corruption, e.g. truncated files that still decode
            partially. Disable to count only hard decoding errors.
        :param timeout: float | None: Seconds to wait for each
            identify run before killing it and reporting the image
            as corrupted. None disables the timeout.

        """
        self.verbose = verbose
        self.regard_warnings = regard_warnings
        self.timeout = timeout

    def check_image_with_imagemagick(
        self,
        file_path: Path
            ) -> tuple[int, bytes, bytes]:
        """
        Check if image is corrupted with identify function of ImageMagick.
        A run longer than self.timeout seconds is killed, leaving a
            non-zero exit code.
        :param file_path: Path: Image path.

        """

        identify_command = ["identify"]
        if self.regard_warnings:
            identify_command.append("-regard-warnings")
        identify_command += ["-verbose", str(file_path)]

        proc = Popen(
            identify_command,
            stdout=PIPE,
            stderr=PIPE
            )
        try:
            out, err = proc.communicate(timeout=self.timeout)
        except TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        exitcode = proc.returncode
        return exitcode, out, err

    def is_image_corrupted(
        self,
        file_path: Path
            ) -> tuple[Path, bool]:
        """
        Determine if an image is corrupted based on the
            exit code of check_image_with_imagemagick.
        ImageMagick warnings count as corruption only while
            regard_warnings is enabled, which is the default.
        :param file_path: Path: Image path.

        """

        exitcode, _out, _err = self.check_image_with_imagemagick(file_path)

        corrupted = exitcode != 0

        if self.verbose:
            print(f"Path: {file_path}, corrupted: {corrupted}")

        return file_path, corrupted

    def get_files_to_check(
        self,
        folder_to_check: Path, file_extensions_list: list[str]
            ) -> list[Path]:
        """
        Get list of file Paths to check. The folder is scanned
            recursively and extensions are matched case-insensitively.
        :param folder_to_check: Path: Folder to check for corrupted images.
        :param file_extensions_list: list[str]:
            List of image extensions to check.

        """

        if not folder_to_check.is_dir():
            raise FileNotFoundError(
                f"{folder_to_check} is not an existing folder."
                )

        extensions_to_check = {
            extension.lstrip(".").lower()
            for extension in file_extensions_list
            }

        return [
            file for file in folder_to_check.rglob("*")
            if file.is_file()
            and file.suffix.lstrip(".").lower() in extensions_to_check
            ]

    def check_images_on_pool(
        self,
        list_of_files_to_check: list[Path],
        max_workers: int | None
            ) -> Iterator[tuple[Path, bool]]:
        """
        Check images concurrently using concurrent.futures.ProcessPoolExecutor.

        :param list_of_files_to_check: list[Path]: List of images to check.
        :param max_workers: int | None: Max workers to use concurrently.
            None uses one worker per CPU.

        """

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            return executor.map(
                self.is_image_corrupted,
                list_of_files_to_check
                )

    def get_corrupted_images(
        self,
        folder_to_check: Path,
        file_extensions_list: list[str],
        max_workers: int | None = None
            ) -> list[Path]:
        """
        Check for corrupted images on a folder.
        :param folder_to_check: Path: Folder to check for corrupted images.
        :param file_extensions_list: list[str]:
            List of image extensions to check.
        :param max_workers: int | None:  (Default value = None)
            Max workers to use concurrently. None uses one worker
            per CPU.

        """

        files_to_check = self.get_files_to_check(
            folder_to_check=folder_to_check,
            file_extensions_list=file_extensions_list
            )

        checked_image_list = list(
            self.check_images_on_pool(
                list_of_files_to_check=files_to_check,
                max_workers=max_workers
                )
            )

        # Return corrupted images.
        return [
            file_path for file_path, corrupted in checked_image_list
            if corrupted
            ]
