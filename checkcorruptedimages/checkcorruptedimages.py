#!/usr/bin/env python3

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

from checkcorruptedimages._pool import StickyWorkerPool
from checkcorruptedimages._result import ImageCheckResult


class CheckCorruptedImages:
    """
    Python class to check for corrupted images by fully decoding them
        with Pillow inside sacrificial worker processes: a decoder
        crash or hang only kills a worker, never this process.
    """
    def __init__(
        self,
        verbose: bool = False,
        regard_warnings: bool = True,
        timeout: float | None = 60,
        max_worker_memory: int | None = None,
        *,
        _worker_command: list[str] | None = None
            ):
        """
        :param verbose: bool: Print the status of each checked image.
        :param regard_warnings: bool: Treat Pillow warnings and
            truncated files that would still partially decode as
            corruption. Disable to count only files Pillow cannot
            decode at all.
        :param timeout: float | None: Seconds to wait for each image
            before killing the decoder and reporting the image as
            corrupted. None disables the timeout.
        :param max_worker_memory: int | None: Best-effort memory cap
            in bytes for each decoder worker (POSIX only). A decode
            over the cap fails and the image is reported as
            corrupted.

        """
        self.verbose = verbose
        self.regard_warnings = regard_warnings
        self.timeout = timeout
        self.max_worker_memory = max_worker_memory
        self._worker_command = _worker_command

    def _build_worker_command(self) -> list[str]:
        if self._worker_command is not None:
            return self._worker_command
        mode = "--strict" if self.regard_warnings else "--lenient"
        worker_command = [
            sys.executable, "-m", "checkcorruptedimages._worker", mode
            ]
        if self.max_worker_memory is not None:
            worker_command += ["--max-memory", str(self.max_worker_memory)]
        return worker_command

    def _print_result(self, result: ImageCheckResult) -> None:
        line = f"Path: {result.file_path}, corrupted: {result.corrupted}"
        if result.corrupted and result.reason is not None:
            line += f", reason: {result.reason}"
        print(line)

    def check_files(
        self,
        list_of_files_to_check: list[Path],
        max_workers: int | None = None,
        on_result: Callable[[ImageCheckResult], None] | None = None
            ) -> list[ImageCheckResult]:
        """
        Check images concurrently on a pool of persistent worker
            processes; this is the fast path, workers are reused
            across the whole batch.
        :param list_of_files_to_check: list[Path]: Images to check.
        :param max_workers: int | None: Max workers to use
            concurrently. None uses one worker per CPU.
        :param on_result: Called with each ImageCheckResult in
            completion order; useful for progress reporting.

        """

        pool = StickyWorkerPool(
            worker_command=self._build_worker_command(),
            max_workers=max_workers,
            timeout=self.timeout,
            result_callback=self._print_result if self.verbose else None
            )
        return pool.run(list_of_files_to_check, on_result=on_result)

    def is_image_corrupted(
        self,
        file_path: Path
            ) -> tuple[Path, bool]:
        """
        Determine if a single image is corrupted. Spawns one worker
            per call; prefer the batch methods or a session for many
            images.
        :param file_path: Path: Image path.

        """

        result = self.check_files([file_path], max_workers=1)[0]
        return result.file_path, result.corrupted

    def session(self, max_workers: int | None = None) -> "CheckSession":
        """
        Open a session that keeps decoder workers alive across calls,
            avoiding the worker startup cost on every call. Options
            are captured at this moment; close the session when done
            (or use it as a context manager).
        :param max_workers: int | None: Workers to keep alive.
            None uses one worker per CPU.

        """

        return CheckSession(
            StickyWorkerPool(
                worker_command=self._build_worker_command(),
                max_workers=max_workers,
                timeout=self.timeout,
                result_callback=self._print_result if self.verbose else None
                )
            )

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
        Compatibility wrapper over check_files preserving the 0.x
            return shape; prefer check_files, which also reports the
            corruption reason.
        :param list_of_files_to_check: list[Path]: List of images to check.
        :param max_workers: int | None: Max workers to use concurrently.
            None uses one worker per CPU.

        """

        return iter(
            [
                (result.file_path, result.corrupted)
                for result in self.check_files(
                    list_of_files_to_check, max_workers=max_workers
                    )
                ]
            )

    def get_check_results(
        self,
        folder_to_check: Path,
        file_extensions_list: list[str],
        max_workers: int | None = None,
        on_result: Callable[[ImageCheckResult], None] | None = None
            ) -> list[ImageCheckResult]:
        """
        Check a folder and return the full per-image results,
            including the corruption reason.
        :param folder_to_check: Path: Folder to check for corrupted images.
        :param file_extensions_list: list[str]:
            List of image extensions to check.
        :param max_workers: int | None:  (Default value = None)
            Max workers to use concurrently. None uses one worker
            per CPU.
        :param on_result: Called with each ImageCheckResult in
            completion order; useful for progress reporting.

        """

        files_to_check = self.get_files_to_check(
            folder_to_check=folder_to_check,
            file_extensions_list=file_extensions_list
            )
        return self.check_files(
            files_to_check, max_workers=max_workers, on_result=on_result
            )

    def get_corrupted_images(
        self,
        folder_to_check: Path,
        file_extensions_list: list[str],
        max_workers: int | None = None,
        on_result: Callable[[ImageCheckResult], None] | None = None
            ) -> list[Path]:
        """
        Check for corrupted images on a folder.
        :param folder_to_check: Path: Folder to check for corrupted images.
        :param file_extensions_list: list[str]:
            List of image extensions to check.
        :param max_workers: int | None:  (Default value = None)
            Max workers to use concurrently. None uses one worker
            per CPU.
        :param on_result: Called with each ImageCheckResult in
            completion order; useful for progress reporting.

        """

        return [
            result.file_path
            for result in self.get_check_results(
                folder_to_check=folder_to_check,
                file_extensions_list=file_extensions_list,
                max_workers=max_workers,
                on_result=on_result
                )
            if result.corrupted
            ]


class CheckSession:
    """
    Keeps decoder workers alive across calls. Not thread-safe: run
        one batch at a time from a single thread.
    """

    def __init__(self, pool: StickyWorkerPool):
        self._pool = pool
        self._closed = False
        self._pool.start()

    # typing.Self needs Python 3.11; the floor is 3.10.
    def __enter__(self) -> "CheckSession":  # noqa: PYI034
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Terminate the workers; the session cannot be used again."""

        if not self._closed:
            self._closed = True
            self._pool.close()

    def check_files(
        self,
        list_of_files_to_check: list[Path],
        on_result: Callable[[ImageCheckResult], None] | None = None
            ) -> list[ImageCheckResult]:
        """
        Check images on the session's persistent workers.
        :param list_of_files_to_check: list[Path]: Images to check.
        :param on_result: Called with each ImageCheckResult in
            completion order; useful for progress reporting.

        """

        if self._closed:
            raise RuntimeError("The session is closed.")
        return self._pool.run(list_of_files_to_check, on_result=on_result)

    def is_image_corrupted(
        self,
        file_path: Path
            ) -> tuple[Path, bool]:
        """
        Determine if a single image is corrupted without paying the
            worker startup cost per call.
        :param file_path: Path: Image path.

        """

        result = self.check_files([file_path])[0]
        return result.file_path, result.corrupted
