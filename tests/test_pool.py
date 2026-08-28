#!/usr/bin/env python3

import sys
import time
from pathlib import Path

import pytest

from checkcorruptedimages._pool import StickyWorkerPool, WorkerStartupError
from checkcorruptedimages._result import REASON_CRASHED, REASON_TIMEOUT

FAKE_OK = """\
import json
import sys

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"status": "ok", "reason": None}), flush=True)
"""

FAKE_ECHO = """\
import json
import sys

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    print(
        json.dumps({"status": "corrupted", "reason": request["path"]}),
        flush=True
        )
"""

FAKE_CRASH = """\
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

FAKE_SLEEP = """\
import json
import sys
import time

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if "SLEEPME" in request["path"]:
        time.sleep(3600)
    print(json.dumps({"status": "ok", "reason": None}), flush=True)
"""

FAKE_STDERR_FLOOD = """\
import json
import sys

print(json.dumps({"status": "ready"}), flush=True)
for line in sys.stdin:
    json.loads(line)
    sys.stderr.write("x" * 1_000_000)
    sys.stderr.flush()
    print(json.dumps({"status": "ok", "reason": None}), flush=True)
"""

FAKE_PID = """\
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

FAKE_STDIN_CLOSER = """\
import json
import os
import sys
import time

print(json.dumps({"status": "ready"}), flush=True)
line = sys.stdin.readline()
json.loads(line)
print(json.dumps({"status": "ok", "reason": None}), flush=True)
os.close(0)
time.sleep(3600)
"""

FAKE_DEAD_ON_ARRIVAL = """\
import sys

sys.exit(1)
"""

FAKE_SLOW_READY = """\
import time

time.sleep(3600)
"""


def command(source: str) -> list[str]:
    return [sys.executable, "-c", source]


def make_paths(tmp_path: Path, names: list[str]) -> list[Path]:
    return [tmp_path / name for name in names]


class TestStickyWorkerPool:
    def test_results_in_input_order(self, tmp_path):
        files = make_paths(tmp_path, [f"f{i:02}.jpg" for i in range(20)])
        pool = StickyWorkerPool(
            worker_command=command(FAKE_OK), max_workers=4, timeout=None
            )

        results = pool.run(files)

        assert [result.file_path for result in results] == files
        assert not any(result.corrupted for result in results)

    def test_crash_marks_only_culprit_and_batch_continues(self, tmp_path):
        files = make_paths(
            tmp_path, ["a.jpg", "CRASHME.jpg", "b.jpg", "c.jpg"]
            )
        pool = StickyWorkerPool(
            worker_command=command(FAKE_CRASH), max_workers=1, timeout=None
            )

        results = pool.run(files)

        assert [result.corrupted for result in results] == [
            False, True, False, False
            ]
        assert results[1].reason == REASON_CRASHED

    def test_crash_recovery_with_parallel_workers(self, tmp_path):
        names = [
            "a.jpg", "CRASHME1.jpg", "b.jpg", "c.jpg", "CRASHME2.jpg",
            "d.jpg", "e.jpg", "CRASHME3.jpg", "f.jpg", "g.jpg",
            ]
        files = make_paths(tmp_path, names)
        pool = StickyWorkerPool(
            worker_command=command(FAKE_CRASH), max_workers=2, timeout=None
            )

        results = pool.run(files)

        corrupted_names = {
            result.file_path.name for result in results if result.corrupted
            }
        assert corrupted_names == {
            "CRASHME1.jpg", "CRASHME2.jpg", "CRASHME3.jpg"
            }
        assert [result.file_path.name for result in results] == names

    def test_timeout_kills_and_batch_continues(self, tmp_path):
        files = make_paths(tmp_path, ["a.jpg", "SLEEPME.jpg", "b.jpg"])
        pool = StickyWorkerPool(
            worker_command=command(FAKE_SLEEP), max_workers=1, timeout=0.5
            )

        start = time.monotonic()
        results = pool.run(files)
        elapsed = time.monotonic() - start

        assert elapsed < 10
        assert [result.corrupted for result in results] == [
            False, True, False
            ]
        assert results[1].reason == REASON_TIMEOUT

    def test_nonexistent_worker_fails_fast(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=["/nonexistent-worker-binary"], max_workers=1
            )

        with pytest.raises(WorkerStartupError):
            pool.run(make_paths(tmp_path, ["a.jpg"]))

    def test_worker_dead_on_arrival_fails_fast(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=command(FAKE_DEAD_ON_ARRIVAL), max_workers=1
            )

        with pytest.raises(WorkerStartupError):
            pool.run(make_paths(tmp_path, ["a.jpg"]))

    def test_ready_timeout_fails_fast(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=command(FAKE_SLOW_READY),
            max_workers=1,
            ready_timeout=0.5
            )

        start = time.monotonic()
        with pytest.raises(WorkerStartupError):
            pool.run(make_paths(tmp_path, ["a.jpg"]))
        elapsed = time.monotonic() - start

        assert elapsed < 10

    def test_stderr_flood_does_not_deadlock(self, tmp_path):
        files = make_paths(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
        pool = StickyWorkerPool(
            worker_command=command(FAKE_STDERR_FLOOD),
            max_workers=1,
            timeout=30
            )

        results = pool.run(files)

        assert not any(result.corrupted for result in results)

    def test_empty_file_list_spawns_nothing(self):
        pool = StickyWorkerPool(
            worker_command=["/nonexistent-worker-binary"], max_workers=4
            )

        assert pool.run([]) == []

    def test_path_round_trip_non_ascii(self, tmp_path):
        weird = tmp_path / "imágen ñ.jpg"
        pool = StickyWorkerPool(
            worker_command=command(FAKE_ECHO), max_workers=1
            )

        results = pool.run([weird])

        assert results[0].reason == str(weird)

    def test_persistent_pool_reuses_workers(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=command(FAKE_PID), max_workers=1
            )

        with pool:
            first = pool.run(make_paths(tmp_path, ["a.jpg"]))[0].reason
            second = pool.run(make_paths(tmp_path, ["b.jpg"]))[0].reason

        assert first == second

    def test_ephemeral_runs_use_fresh_workers(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=command(FAKE_PID), max_workers=1
            )

        first = pool.run(make_paths(tmp_path, ["a.jpg"]))[0].reason
        second = pool.run(make_paths(tmp_path, ["b.jpg"]))[0].reason

        assert first != second

    def test_persistent_pool_survives_crash_between_batches(self, tmp_path):
        pool = StickyWorkerPool(
            worker_command=command(FAKE_CRASH), max_workers=1
            )

        with pool:
            crashed = pool.run(make_paths(tmp_path, ["CRASHME.jpg"]))
            healthy = pool.run(make_paths(tmp_path, ["a.jpg"]))

        assert crashed[0].corrupted is True
        assert crashed[0].reason == REASON_CRASHED
        assert healthy[0].corrupted is False

    def test_write_failure_retries_innocent_file(self, tmp_path):
        files = make_paths(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
        pool = StickyWorkerPool(
            worker_command=command(FAKE_STDIN_CLOSER),
            max_workers=1,
            timeout=30
            )

        results = pool.run(files)

        assert not any(result.corrupted for result in results)

    def test_on_result_streams_in_completion_order(self, tmp_path):
        files = make_paths(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
        seen = []
        pool = StickyWorkerPool(
            worker_command=command(FAKE_OK), max_workers=1, timeout=None
            )

        results = pool.run(files, on_result=seen.append)

        assert seen == results

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="newlines are not allowed in Windows paths"
        )
    def test_path_round_trip_newline(self, tmp_path):
        weird = tmp_path / "line\nbreak.jpg"
        pool = StickyWorkerPool(
            worker_command=command(FAKE_ECHO), max_workers=1
            )

        results = pool.run([weird])

        assert results[0].reason == str(weird)
