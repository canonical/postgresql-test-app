# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import stat
from typing import ClassVar
from unittest.mock import MagicMock, patch

from continuous_reads import (
    _ensure_pipe,
    _format_unit,
    _read_endpoint,
    _run_round,
    _unit_short,
    _write_to_pipe,
)


class TestEnsurePipe:
    def test_creates_fifo(self, tmp_path):
        pipe_path = str(tmp_path / "test.pipe")
        _ensure_pipe(pipe_path)
        assert stat.S_ISFIFO(os.stat(pipe_path).st_mode)

    def test_replaces_regular_file(self, tmp_path):
        pipe_path = str(tmp_path / "test.pipe")
        with open(pipe_path, "w") as f:
            f.write("not a pipe")
        _ensure_pipe(pipe_path)
        assert stat.S_ISFIFO(os.stat(pipe_path).st_mode)

    def test_preserves_existing_fifo(self, tmp_path):
        pipe_path = str(tmp_path / "test.pipe")
        os.mkfifo(pipe_path)
        inode_before = os.stat(pipe_path).st_ino
        _ensure_pipe(pipe_path)
        assert os.stat(pipe_path).st_ino == inode_before


class TestUnitShort:
    def test_strips_app_name(self):
        assert _unit_short("postgresql/0") == "/0"

    def test_strips_k8s_app_name(self):
        assert _unit_short("postgresql-k8s/2") == "/2"

    def test_preserves_ip_fallback(self):
        assert _unit_short("10.0.0.1") == "10.0.0.1"


class TestWriteToPipe:
    def test_no_reader_does_not_hang(self, tmp_path):
        pipe_path = str(tmp_path / "test.pipe")
        os.mkfifo(pipe_path)
        _write_to_pipe(pipe_path, "test line")

    def test_nonexistent_path(self, tmp_path):
        pipe_path = str(tmp_path / "nonexistent.pipe")
        _write_to_pipe(pipe_path, "test line")


class TestFormatUnit:
    def test_normal(self):
        assert _format_unit("/0", 43585, 3, 0) == "/0=43585:+3 []"

    def test_with_gaps(self):
        assert _format_unit("/1", 43605, 3, 2) == "/1=43605:+3 [2]"

    def test_unreachable(self):
        assert _format_unit("/0", -1, 0, 0) == "/0=:+0 []"

    def test_zero_delta(self):
        assert _format_unit("/0", 43599, 0, 0) == "/0=43599:+0 []"


class TestReadEndpoint:
    @patch("continuous_reads.psycopg2")
    def test_read_with_gaps(self, mock_psycopg2):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 100, 98)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn

        max_val, gaps = _read_endpoint("dbname='test' user='u' password='p'", "host1", "5432")

        assert max_val == 100
        assert gaps == 2

    @patch("continuous_reads.psycopg2")
    def test_read_no_gaps(self, mock_psycopg2):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 50, 50)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn

        max_val, gaps = _read_endpoint("dbname='test' user='u' password='p'", "host1", "5432")

        assert max_val == 50
        assert gaps == 0

    @patch("continuous_reads.psycopg2")
    def test_unreachable_endpoint(self, mock_psycopg2):
        mock_psycopg2.connect.side_effect = Exception("connection refused")

        max_val, gaps = _read_endpoint("dbname='test' user='u' password='p'", "host1", "5432")

        assert max_val == -1
        assert gaps == -1

    @patch("continuous_reads.psycopg2")
    def test_empty_table(self, mock_psycopg2):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (None, None, 0)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn

        max_val, gaps = _read_endpoint("dbname='test' user='u' password='p'", "host1", "5432")

        assert max_val == -1
        assert gaps == -1

    @patch("continuous_reads.psycopg2")
    def test_offset_start_no_gaps(self, mock_psycopg2):
        """A table truncated/resumed at a non-1 offset must not report phantom gaps."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (50, 100, 51)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn

        max_val, gaps = _read_endpoint("dbname='test' user='u' password='p'", "host1", "5432")

        assert max_val == 100
        assert gaps == 0


class TestRunRound:
    TEMPLATE = "dbname='test' user='u' password='p'"
    IP_TO_UNIT: ClassVar[dict[str, str]] = {
        "10.0.0.1": "postgresql/0",
        "10.0.0.2": "postgresql/1",
    }

    @patch("continuous_reads._read_endpoint")
    def test_delta_bridges_outage(self, mock_read):
        """Delta must bridge unreachable rounds instead of resetting to +0."""
        prev_max = {}

        mock_read.return_value = (100, 0)
        _run_round(self.TEMPLATE, ["10.0.0.1:5432"], self.IP_TO_UNIT, prev_max)
        assert prev_max == {"/0": 100}

        mock_read.return_value = (-1, -1)
        line = _run_round(self.TEMPLATE, ["10.0.0.1:5432"], self.IP_TO_UNIT, prev_max)
        assert "/0=:+0 []" in line
        assert prev_max == {"/0": 100}, "outage must not clobber the last good value"

        mock_read.return_value = (105, 0)
        line = _run_round(self.TEMPLATE, ["10.0.0.1:5432"], self.IP_TO_UNIT, prev_max)
        assert "/0=105:+5 []" in line, "delta must span the outage, not reset"
        assert prev_max == {"/0": 105}

    @patch("continuous_reads._read_endpoint")
    def test_orders_units_and_formats_line(self, mock_read):
        mock_read.side_effect = lambda _template, host, _port: {
            "10.0.0.1": (10, 0),
            "10.0.0.2": (12, 2),
        }[host]

        line = _run_round(
            self.TEMPLATE,
            ["10.0.0.2:5432", "10.0.0.1:5432"],
            self.IP_TO_UNIT,
            {},
        )

        assert line.endswith("/0=10:+0 [] /1=12:+0 [2]")
