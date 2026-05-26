# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from types import SimpleNamespace
from unittest.mock import Mock

from src.charm import ApplicationCharm


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
    event.params = {"relation-name": "database", "dbname": "db", "query": "SELECT 1", "readonly": False}

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
