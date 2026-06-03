# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Background script that reads the last continuous write from every endpoint.

For each endpoint (all units discovered via per-unit relation data) it queries
the max value and count of rows in the continuous writes table, emitting a
compact status line to a named pipe (FIFO) that can be tailed.

Log line format:
    HH:MM:SS: /0=43585:+3 [] /1=43585:+3 []

Where:
    /N          unit number (stripped app name)
    43585       MAX(number) from continuous_writes (empty when unreachable)
    +3          delta: records inserted since last read round
    []          gap indicator: empty = clean, [2] = 2 records lost
                (holes between MIN and MAX, robust to truncation/offset resumes)
"""

import contextlib
import json
import os
import signal
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from time import sleep

import psycopg2

run = True


def _sigterm_handler(_signo, _stack_frame):
    global run
    run = False


def _ensure_pipe(pipe_path: str) -> None:
    """Create the named pipe (FIFO) if it does not already exist."""
    if os.path.exists(pipe_path):
        if not stat.S_ISFIFO(os.stat(pipe_path).st_mode):
            os.remove(pipe_path)
            os.mkfifo(pipe_path)
    else:
        os.mkfifo(pipe_path)


def _write_to_pipe(pipe_path: str, line: str) -> None:
    """Write a line to the named pipe without blocking when no reader is attached."""
    try:
        fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return

    try:
        os.write(fd, f"{line}\n".encode())
    except OSError:
        pass
    finally:
        os.close(fd)


def _unit_short(unit_name: str) -> str:
    """Turn 'postgresql/0' into '/0'."""
    if "/" in unit_name:
        return "/" + unit_name.split("/", 1)[1]
    return unit_name


def _endpoint_sort_key(endpoint: str, ip_to_unit: dict[str, str]) -> tuple[str, int]:
    """Sort key that orders endpoints by unit number (e.g. /0, /1, /2)."""
    host = endpoint.rsplit(":", 1)[0]
    name = ip_to_unit.get(host, host)
    try:
        return (name.rsplit("/", 1)[0], int(name.rsplit("/", 1)[1]))
    except (ValueError, IndexError):
        return (name, 0)


def _read_config() -> tuple[str, list[str], dict[str, str]]:
    """Read the JSON config file written by the charm."""
    with open("/tmp/continuous_reads_config") as fd:  # noqa: S108
        config = json.load(fd)
    return config["connection_string_template"], config["endpoints"], config.get("ip_to_unit", {})


def _read_endpoint(connection_string_template: str, host: str, port: str) -> tuple[int, int]:
    """Read MIN, MAX and COUNT from one endpoint.

    Returns (max_value, gaps) or (-1, -1) on error. Gaps are holes in the
    sequence between MIN and MAX, so the count stays correct even when the
    table was truncated or writes resumed from a non-1 offset.
    """
    connstr = f"{connection_string_template} host='{host}' port={port}"
    connection = None
    try:
        connection = psycopg2.connect(connstr)
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT MIN(number), MAX(number), COUNT(number) FROM continuous_writes;"
            )
            result = cursor.fetchone()
    except Exception:
        return -1, -1
    finally:
        if connection:
            with contextlib.suppress(Exception):
                connection.close()

    if not result or result[0] is None:
        return -1, -1

    min_val, max_val, count_val = result
    gaps = (max_val - min_val + 1) - count_val
    return max_val, gaps


def _format_unit(label: str, max_val: int, delta: int, gaps: int) -> str:
    """Format one unit's status: /0=43585:+3 [] or /0=:+0 []."""
    max_str = str(max_val) if max_val >= 0 else ""
    gap_str = f"[{gaps}]" if gaps > 0 else "[]"
    return f"{label}={max_str}:+{delta} {gap_str}"


def _run_round(
    connection_string_template: str,
    endpoints: list[str],
    ip_to_unit: dict[str, str],
    prev_max: dict[str, int],
) -> str:
    """Read all endpoints concurrently and return one formatted status line.

    Concurrent reads cap the round duration at roughly one connect_timeout,
    so a single unreachable endpoint cannot stall monitoring of the others.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    ordered = sorted(endpoints, key=lambda ep: _endpoint_sort_key(ep, ip_to_unit))

    with ThreadPoolExecutor(max_workers=len(ordered)) as pool:
        results = list(
            pool.map(
                lambda ep: _read_endpoint(connection_string_template, *ep.rsplit(":", 1)),
                ordered,
            )
        )

    parts: list[str] = []
    for endpoint, (max_val, gap_val) in zip(ordered, results, strict=True):
        host = endpoint.rsplit(":", 1)[0]
        label = _unit_short(ip_to_unit.get(host, host))

        prev = prev_max.get(label, -1)
        delta = max_val - prev if max_val >= 0 and prev >= 0 else 0
        if max_val >= 0:
            # Keep the last good value across outages so the delta bridges
            # unreachable rounds instead of silently resetting to +0.
            prev_max[label] = max_val

        parts.append(_format_unit(label, max_val, delta, gap_val if max_val >= 0 else 0))

    return f"{timestamp}: {' '.join(parts)}"


def continuous_reads(pipe_path: str, read_interval: int) -> None:
    """Continuously read from every endpoint, logging compact status to a pipe."""
    _ensure_pipe(pipe_path)

    prev_max: dict[str, int] = {}

    while run:
        try:
            connection_string_template, endpoints, ip_to_unit = _read_config()
        except (FileNotFoundError, json.JSONDecodeError):
            # Config is removed by the charm just before SIGTERM, and may be
            # mid-rewrite on an update. Skip this round rather than crashing.
            sleep(0.1)
            continue

        if not endpoints:
            sleep(0.1)
            continue

        line = _run_round(connection_string_template, endpoints, ip_to_unit, prev_max)
        _write_to_pipe(pipe_path, line)

        if read_interval:
            sleep(read_interval / 1000)


def main():
    """Run the continuous reads script."""
    [_, read_interval, pipe_path] = sys.argv

    continuous_reads(pipe_path, int(read_interval))


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _sigterm_handler)
    main()
