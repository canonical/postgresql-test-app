# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from types import SimpleNamespace
from unittest.mock import Mock

from ops import ActiveStatus, BlockedStatus

from src.charm import BLOCKED_NO_INTEGRATION_MSG, ApplicationCharm


def test_on_start_sets_blocked_when_no_relation_data():
    """Unit stays blocked on start when no database credentials exist."""
    empty_db = Mock()
    empty_db.fetch_relation_data.return_value = {}

    charm = SimpleNamespace(
        database=empty_db,
        second_database=Mock(fetch_relation_data=Mock(return_value={})),
        database_clusters=Mock(fetch_relation_data=Mock(return_value={})),
        aliased_database_clusters=Mock(fetch_relation_data=Mock(return_value={})),
        unit=Mock(),
        model=Mock(),
        app_peer_data={},
    )
    charm.model.unit.is_leader.return_value = False

    event = Mock()
    ApplicationCharm._on_start(charm, event)

    assert charm.unit.status == BlockedStatus(BLOCKED_NO_INTEGRATION_MSG)


def test_on_start_sets_active_when_credentials_present():
    """Unit transitions to active on start when database credentials are present."""
    populated_db = Mock()
    populated_db.fetch_relation_data.return_value = {
        1: {"username": "test_user", "password": "test_pass"}
    }

    charm = SimpleNamespace(
        database=populated_db,
        second_database=Mock(fetch_relation_data=Mock(return_value={})),
        database_clusters=Mock(fetch_relation_data=Mock(return_value={})),
        aliased_database_clusters=Mock(fetch_relation_data=Mock(return_value={})),
        unit=Mock(),
        model=Mock(),
        app_peer_data={},
    )
    charm.model.unit.is_leader.return_value = False

    event = Mock()
    ApplicationCharm._on_start(charm, event)

    assert charm.unit.status == ActiveStatus("received database credentials of the first database")


def test_connection_string_none_when_relation_data_is_empty():
    charm = Mock()
    charm.database.fetch_relation_data.return_value = {}

    assert ApplicationCharm._connection_string.fget(charm) is None


def test_run_sql_action_fails_cleanly_without_relation_data():
    database = Mock()
    database.relation_name = "database"
    database.fetch_relation_data.return_value = {}

    charm = SimpleNamespace(
        database=database, second_database=Mock(relation_name="second-database")
    )
    charm.connect_to_database = Mock()

    event = Mock()
    event.params = {
        "relation-name": "database",
        "dbname": "db",
        "query": "SELECT 1",
        "readonly": False,
    }

    ApplicationCharm._on_run_sql_action(charm, event)

    event.fail.assert_called_once_with(message="relation data not available yet")
    charm.connect_to_database.assert_not_called()


def test_test_tls_action_fails_cleanly_without_relation_data():
    database = Mock()
    database.relation_name = "database"
    database.fetch_relation_data.return_value = {}

    charm = SimpleNamespace(
        database=database, second_database=Mock(relation_name="second-database")
    )
    charm.connect_to_database = Mock()

    event = Mock()
    event.params = {"relation-name": "database", "dbname": "db", "readonly": False}

    ApplicationCharm._on_test_tls_action(charm, event)

    event.fail.assert_called_once_with(message="relation data not available yet")
    charm.connect_to_database.assert_not_called()
