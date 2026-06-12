# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, mock_open, patch

from ops import testing

from charm import BLOCKED_NO_INTEGRATION_MSG, CONFIG_FILE, PROC_PID_KEY, ApplicationCharm

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx():
    """Create a fresh Context for ApplicationCharm."""
    return testing.Context(ApplicationCharm, juju_version="4.0.0")


def _state(
    *,
    leader: bool = False,
    peer_data: dict | None = None,
    extra_relations: list | None = None,
) -> testing.State:
    """Build a State with the peer relation and optional app peer data."""
    peer = testing.PeerRelation(
        endpoint="postgresql-test-peers",
        local_app_data=peer_data or {},
    )
    return testing.State(leader=leader, relations=[peer, *(extra_relations or [])])


def _database_relation(endpoint: str) -> testing.Relation:
    """Build a database relation whose databag carries credentials."""
    return testing.Relation(
        endpoint=endpoint,
        remote_app_name="pg",
        remote_app_data={"username": "user", "password": "pass"},
    )


# ---------------------------------------------------------------------------
# Task 4: _on_start tests
# ---------------------------------------------------------------------------


def test_on_start_no_relations():
    ctx = _ctx()
    state_in = _state(leader=False)
    with patch("charm.DatabaseRequires.fetch_relation_data", return_value={}):
        state_out = ctx.run(ctx.on.start(), state_in)
    assert state_out.unit_status == testing.BlockedStatus(BLOCKED_NO_INTEGRATION_MSG)


def test_on_start_with_database_credentials():
    ctx = _ctx()
    state_in = _state(leader=False, extra_relations=[_database_relation("database")])

    state_out = ctx.run(ctx.on.start(), state_in)
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials of the first database"
    )


def test_on_start_with_second_database_credentials():
    ctx = _ctx()
    state_in = _state(leader=False, extra_relations=[_database_relation("second-database")])

    state_out = ctx.run(ctx.on.start(), state_in)
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials of the second database"
    )


def test_on_start_with_cluster_credentials():
    ctx = _ctx()
    state_in = _state(
        leader=False, extra_relations=[_database_relation("multiple-database-clusters")]
    )

    state_out = ctx.run(ctx.on.start(), state_in)
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials for a database cluster"
    )


def test_on_start_with_aliased_cluster_credentials():
    ctx = _ctx()
    state_in = _state(
        leader=False, extra_relations=[_database_relation("aliased-multiple-database-clusters")]
    )

    state_out = ctx.run(ctx.on.start(), state_in)
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials for an aliased database cluster"
    )


def test_on_start_restarts_writes():
    ctx = _ctx()
    state_in = _state(leader=True, peer_data={PROC_PID_KEY: "12345"})
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        patch.object(ApplicationCharm, "are_writes_running", return_value=False),
        patch.object(ApplicationCharm, "_get_db_writes", return_value=5),
        patch.object(ApplicationCharm, "_start_continuous_writes") as mock_start,
    ):
        state_out = ctx.run(ctx.on.start(), state_in)
        mock_start.assert_called_once_with(6)
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials of the first database"
    )


def test_on_start_writes_zero():
    ctx = _ctx()
    state_in = _state(leader=True, peer_data={PROC_PID_KEY: "12345"})
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        patch.object(ApplicationCharm, "are_writes_running", return_value=False),
        patch.object(ApplicationCharm, "_get_db_writes", return_value=0),
        patch.object(ApplicationCharm, "_start_continuous_writes") as mock_start,
    ):
        state_out = ctx.run(ctx.on.start(), state_in)
        mock_start.assert_not_called()
    # Line 214 hardcodes this message unconditionally when entering the write-restart block
    assert state_out.unit_status == testing.ActiveStatus(
        "received database credentials of the first database"
    )


def test_on_start_defers_on_db_error():
    ctx = _ctx()
    state_in = _state(leader=True, peer_data={PROC_PID_KEY: "12345"})
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        patch.object(ApplicationCharm, "are_writes_running", return_value=False),
        patch.object(
            ApplicationCharm, "_get_db_writes", side_effect=Exception("connection refused")
        ),
    ):
        state_out = ctx.run(ctx.on.start(), state_in)
    # Early return on line 209 prevents reaching the hardcoded ActiveStatus on line 214.
    # Status remains BlockedStatus from the credential loop (no creds mocked).
    assert state_out.unit_status == testing.BlockedStatus(BLOCKED_NO_INTEGRATION_MSG)


# ---------------------------------------------------------------------------
# Task 5: Database relation handler tests
# ---------------------------------------------------------------------------


def test_on_database_created():
    ctx = _ctx()
    state_in = _state()
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        ctx(ctx.on.start(), state_in) as mgr,
    ):
        mgr.charm._on_database_created(MagicMock())
        assert mgr.charm.unit.status == testing.ActiveStatus(
            "received database credentials of the first database"
        )


def test_on_database_endpoints_changed_updates_config():
    conn_string = "dbname='test' user='u' host='h' password='p' port=5432 connect_timeout=5"
    ctx = _ctx()
    state_in = _state(peer_data={PROC_PID_KEY: "12345"})
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        patch.object(
            ApplicationCharm,
            "_connection_string",
            new_callable=lambda: property(lambda self: conn_string),
        ),
        patch("builtins.open", mock_open()) as mock_file,
        patch("charm.os.fsync"),
        ctx(ctx.on.start(), state_in) as mgr,
    ):
        mgr.charm._on_database_endpoints_changed(MagicMock())
        mock_file.assert_called_once_with(CONFIG_FILE, "w")
        mock_file().write.assert_called_once_with(conn_string)


def test_on_database_endpoints_changed_no_proc_pid():
    conn_string = "dbname='test' user='u' host='h' password='p' port=5432 connect_timeout=5"
    ctx = _ctx()
    state_in = _state()
    with (
        patch("charm.DatabaseRequires.fetch_relation_data", return_value={}),
        patch.object(
            ApplicationCharm,
            "_connection_string",
            new_callable=lambda: property(lambda self: conn_string),
        ),
        patch("builtins.open", mock_open()) as mock_file,
        ctx(ctx.on.start(), state_in) as mgr,
    ):
        mgr.charm._on_database_endpoints_changed(MagicMock())
        mock_file.assert_not_called()


def test_on_relation_broken_no_remaining():
    ctx = _ctx()
    rel = testing.Relation(endpoint="database", remote_app_name="pg")
    peer = testing.PeerRelation(endpoint="postgresql-test-peers")
    state_in = testing.State(leader=False, relations=[peer, rel])
    state_out = ctx.run(ctx.on.relation_broken(rel), state_in)
    assert state_out.unit_status == testing.BlockedStatus(BLOCKED_NO_INTEGRATION_MSG)


# ---------------------------------------------------------------------------
# Task 6: Continuous writes action tests
# ---------------------------------------------------------------------------


def _mock_psycopg2_connect():
    """Return a mock psycopg2.connect that supports double context manager."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connect, mock_conn, mock_cursor


def test_start_continuous_writes_action_success():
    mock_connect, _mock_conn, mock_cursor = _mock_psycopg2_connect()
    mock_cursor.fetchone.return_value = (0,)
    conn_string = "dbname='test' user='u' host='h' password='p' port=5432 connect_timeout=5"
    ctx = _ctx()
    state_in = _state(leader=True)
    with (
        patch.object(
            ApplicationCharm,
            "_connection_string",
            new_callable=lambda: property(lambda self: conn_string),
        ),
        patch("charm.psycopg2.connect", mock_connect),
        patch("charm.subprocess.Popen") as mock_popen,
        patch("builtins.open", mock_open()),
        patch("charm.os.fsync"),
        patch("charm.os.kill"),
        patch("charm.os.remove"),
    ):
        mock_popen.return_value.pid = 99999
        state_out = ctx.run(ctx.on.action("start-continuous-writes"), state_in)
    assert ctx.action_results["result"] == "True"
    # Check the peer data was updated with the process PID
    peer_rel = next(r for r in state_out.relations if r.endpoint == "postgresql-test-peers")
    assert peer_rel.local_app_data[PROC_PID_KEY] == "99999"


def test_start_continuous_writes_action_no_connection():
    ctx = _ctx()
    state_in = _state(leader=True)
    with patch.object(
        ApplicationCharm,
        "_connection_string",
        new_callable=lambda: property(lambda self: None),
    ):
        ctx.run(ctx.on.action("start-continuous-writes"), state_in)
    assert ctx.action_results["result"] == "False"


def test_stop_continuous_writes_action():
    ctx = _ctx()
    state_in = _state(leader=True, peer_data={PROC_PID_KEY: "12345"})
    with (
        patch("charm.os.kill"),
        patch("builtins.open", mock_open(read_data="42")),
        patch("charm.os.remove"),
    ):
        ctx.run(ctx.on.action("stop-continuous-writes"), state_in)
    assert ctx.action_results["writes"] == 42


def test_show_continuous_writes_action():
    ctx = _ctx()
    state_in = _state(leader=True)
    with patch.object(ApplicationCharm, "_get_db_writes", return_value=100):
        ctx.run(ctx.on.action("show-continuous-writes"), state_in)
    assert ctx.action_results["writes"] == 100


def test_clear_continuous_writes_action():
    mock_connect, _mock_conn, mock_cursor = _mock_psycopg2_connect()
    conn_string = "dbname='test' user='u' host='h' password='p' port=5432 connect_timeout=5"
    ctx = _ctx()
    state_in = _state(leader=True)
    with (
        patch.object(
            ApplicationCharm,
            "_connection_string",
            new_callable=lambda: property(lambda self: conn_string),
        ),
        patch("charm.psycopg2.connect", mock_connect),
        patch.object(ApplicationCharm, "_stop_continuous_writes"),
    ):
        ctx.run(ctx.on.action("clear-continuous-writes"), state_in)
    assert ctx.action_results["result"] == "True"
    mock_cursor.execute.assert_any_call("DROP TABLE IF EXISTS continuous_writes;")
