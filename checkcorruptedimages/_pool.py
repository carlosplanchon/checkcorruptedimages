#!/usr/bin/env python3

"""
Pool of persistent sacrificial worker subprocesses.

Workers receive one image path per JSON line on stdin and answer with
one JSON line on stdout, in strict lockstep. A worker that crashes or
exceeds the per-image timeout is killed and respawned; the image it
was processing is reported as corrupted and the batch continues.
"""

import json
import os
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from queue import Queue
from typing import Any

from checkcorruptedimages._result import (
    REASON_CRASHED,
    REASON_TIMEOUT,
    ImageCheckResult,
)

_SHUTDOWN_WAIT = 5.0


class WorkerStartupError(RuntimeError):
    """A worker process could not be started or never became ready."""


def default_max_workers() -> int:
    """One worker per CPU available to this process."""
    if hasattr(os, "process_cpu_count"):
        count = os.process_cpu_count()
    else:
        count = os.cpu_count()
    return count or 1


def _parse(line: str) -> dict[str, Any] | None:
    # A worker killed mid-write can leave a partial line; treat any
    # unparsable payload as a dead worker.
    if not line:
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


class _Worker:
    """
    One child process plus the in-flight state guarded by its lock.
    Only its owner thread dispatches work; the per-request timer only
        kills the process, never mutates anything else.
    """

    def __init__(self, command: list[str], ready_timeout: float | None):
        self.command = command
        self.ready_timeout = ready_timeout
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[str] | None = None
        self.inflight_seq = 0
        self.timer_fired = False
        self.needs_respawn = False

    def is_ready(self) -> bool:
        return (
            self.proc is not None
            and not self.needs_respawn
            and self.proc.poll() is None
            )

    def spawn(self) -> None:
        """Start the child and wait for its ready line."""

        self.shutdown()
        try:
            proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1
                )
        except OSError as error:
            raise WorkerStartupError(
                f"cannot start worker {self.command}: {error}"
                ) from error
        with self.lock:
            self.proc = proc
            self.needs_respawn = False
            self.timer_fired = False

        line = self._read_line(proc, self.ready_timeout, seq=None)
        payload = _parse(line)
        if payload is None or payload.get("status") != "ready":
            self.shutdown()
            raise WorkerStartupError(
                f"worker {self.command} did not become ready"
                )

    def process(
        self,
        file_path: Path,
        timeout: float | None
            ) -> tuple[bool, str | None] | None:
        """
        Check one image on the live worker.
        Returns (corrupted, reason); a crash or timeout reports the
            image as corrupted and leaves the worker flagged for
            respawn by the owner thread. Returns None when the worker
            died before receiving the request, so the owner can retry
            the file on a fresh worker.
        """

        proc = self.proc
        assert proc is not None and proc.stdin is not None

        with self.lock:
            self.inflight_seq += 1
            seq = self.inflight_seq
            self.timer_fired = False

        line = ""
        write_ok = True
        try:
            proc.stdin.write(json.dumps({"path": str(file_path)}) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            write_ok = False
        else:
            line = self._read_line(proc, timeout, seq=seq)

        payload = _parse(line)

        with self.lock:
            # Invalidate the sequence so a timer that fires from now
            # on becomes a no-op.
            self.inflight_seq += 1
            fired = self.timer_fired
            if payload is not None and fired:
                # The kill raced a response that was already in the
                # pipe: keep the real verdict, replace the worker.
                self.needs_respawn = True

        if payload is not None:
            return payload.get("status") != "ok", payload.get("reason")

        self.shutdown()
        if fired:
            return True, REASON_TIMEOUT
        if not write_ok:
            # The worker died before it ever received this file; the
            # file is innocent.
            return None
        return True, REASON_CRASHED

    def _read_line(
        self,
        proc: subprocess.Popen[str],
        timeout: float | None,
        seq: int | None
            ) -> str:
        """
        Blocking readline with a kill-based deadline. For the ready
            line (seq=None) the timer kills unconditionally; for a
            request it kills only while that request is in flight.
        """

        assert proc.stdout is not None
        timer = None
        if timeout is not None:
            timer = threading.Timer(
                timeout, self._deadline_kill, args=(seq,)
                )
            timer.daemon = True
            timer.start()
        try:
            line: str = proc.stdout.readline()
            return line
        finally:
            if timer is not None:
                timer.cancel()

    def _deadline_kill(self, seq: int | None) -> None:
        with self.lock:
            if seq is not None and seq != self.inflight_seq:
                return
            self.timer_fired = True
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()

    def kill(self) -> None:
        """Unblock the owner thread by killing the child."""

        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()

    def shutdown(self) -> None:
        """Terminate and reap the child; safe to call repeatedly."""

        with self.lock:
            proc = self.proc
            self.proc = None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=_SHUTDOWN_WAIT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _spawn_all(workers: list[_Worker]) -> None:
    """Spawn every worker, cleaning up the spawned ones on failure."""

    spawned = []
    try:
        for worker in workers:
            worker.spawn()
            spawned.append(worker)
    except WorkerStartupError:
        for worker in spawned:
            worker.shutdown()
        raise


class StickyWorkerPool:
    """
    Runs a batch of image checks across persistent worker processes.
    """

    def __init__(
        self,
        worker_command: list[str],
        max_workers: int | None = None,
        timeout: float | None = None,
        result_callback: Callable[[ImageCheckResult], None] | None = None,
        ready_timeout: float | None = 30.0
            ):
        """
        :param worker_command: list[str]: Command of the worker
            subprocess speaking the JSON-lines protocol.
        :param max_workers: int | None: Workers to run concurrently.
            None uses one worker per CPU.
        :param timeout: float | None: Seconds allowed per image before
            the worker is killed. None disables the deadline.
        :param result_callback: Called with each ImageCheckResult in
            completion order, serialized under a lock.
        :param ready_timeout: float | None: Seconds allowed for a
            spawned worker to print its ready line.

        """
        self.worker_command = list(worker_command)
        self.max_workers = (
            max_workers if max_workers is not None else default_max_workers()
            )
        self.timeout = timeout
        self.result_callback = result_callback
        self.ready_timeout = ready_timeout
        self._workers: list[_Worker] | None = None

    def start(self) -> None:
        """
        Spawn the workers now and keep them alive across run() calls
            until close(). A started pool runs one batch at a time;
            it is not thread-safe.
        """

        if self._workers is not None:
            return
        workers = [
            _Worker(self.worker_command, self.ready_timeout)
            for _ in range(max(1, self.max_workers))
            ]
        _spawn_all(workers)
        self._workers = workers

    def close(self) -> None:
        """Terminate the persistent workers, if any."""

        workers = self._workers
        self._workers = None
        if workers is None:
            return
        for worker in workers:
            worker.shutdown()

    # typing.Self needs Python 3.11; the floor is 3.10.
    def __enter__(self) -> "StickyWorkerPool":  # noqa: PYI034
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def run(
        self,
        files: Sequence[Path],
        on_result: Callable[[ImageCheckResult], None] | None = None
            ) -> list[ImageCheckResult]:
        """
        Check every file; returns results in input order.
        :param files: Sequence[Path]: Image paths to check.
        :param on_result: Called with each ImageCheckResult in
            completion order, serialized under a lock; composed with
            the pool-level result_callback.

        """

        files = list(files)
        if not files:
            return []

        workers = self._workers
        persistent = workers is not None
        if workers is None:
            worker_count = max(1, min(self.max_workers, len(files)))
            workers = [
                _Worker(self.worker_command, self.ready_timeout)
                for _ in range(worker_count)
                ]
            _spawn_all(workers)

        task_queue: Queue[tuple[int, Path] | None] = Queue()
        for item in enumerate(files):
            task_queue.put(item)
        # One shutdown sentinel per worker.
        for _ in range(len(workers)):
            task_queue.put(None)

        results: list[ImageCheckResult | None] = [None] * len(files)
        abort = threading.Event()
        callback_lock = threading.Lock()
        callbacks = [
            callback
            for callback in (self.result_callback, on_result)
            if callback is not None
            ]
        spawn_errors: list[WorkerStartupError] = []
        spawn_errors_lock = threading.Lock()

        def owner(worker: _Worker) -> None:
            try:
                while not abort.is_set():
                    if not worker.is_ready():
                        try:
                            worker.spawn()
                        except WorkerStartupError as error:
                            # This lane is broken; other workers keep
                            # draining the queue. Never mark files
                            # corrupted because the tool itself broke.
                            with spawn_errors_lock:
                                spawn_errors.append(error)
                            return
                    item = task_queue.get()
                    if item is None:
                        return
                    if abort.is_set():
                        return
                    index, file_path = item
                    outcome = worker.process(file_path, self.timeout)
                    if outcome is None:
                        # The worker died before receiving the file:
                        # retry it once on a fresh worker.
                        try:
                            worker.spawn()
                        except WorkerStartupError as error:
                            with spawn_errors_lock:
                                spawn_errors.append(error)
                            return
                        outcome = worker.process(file_path, self.timeout)
                        if outcome is None:
                            outcome = (True, REASON_CRASHED)
                    corrupted, reason = outcome
                    result = ImageCheckResult(
                        file_path=file_path,
                        corrupted=corrupted,
                        reason=reason
                        )
                    results[index] = result
                    if callbacks:
                        with callback_lock:
                            for callback in callbacks:
                                callback(result)
            finally:
                if not persistent:
                    worker.shutdown()

        threads = [
            threading.Thread(target=owner, args=(worker,), daemon=True)
            for worker in workers
            ]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        except BaseException:
            abort.set()
            for worker in workers:
                worker.kill()
            for thread in threads:
                thread.join(timeout=_SHUTDOWN_WAIT)
            if persistent:
                self.close()
            raise

        if any(result is None for result in results):
            cause = spawn_errors[0] if spawn_errors else None
            raise RuntimeError(
                "The worker pool failed before every file was checked."
                ) from cause

        return [result for result in results if result is not None]
