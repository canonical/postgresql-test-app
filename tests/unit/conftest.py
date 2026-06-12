# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import contextlib

import pytest
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequiresEvents

# Dynamic event attributes registered by DatabaseRequirerEventHandlers for
# cluster aliases.  They are set on the *class* (DatabaseRequiresEvents) via
# define_event, so they persist across test runs.  We must remove them
# after each test so the next Context can re-define them without hitting the
# "overlaps with existing type" RuntimeError.
_DYNAMIC_EVENTS = [
    f"{alias}_{suffix}"
    for alias in ("cluster1", "cluster2")
    for suffix in (
        "database_created",
        "database_entity_created",
        "endpoints_changed",
        "read_only_endpoints_changed",
        "prefix_databases_changed",
    )
]


@pytest.fixture(autouse=True)
def _cleanup_dynamic_events():
    """Clean up dynamically-defined events so the next test can re-register them."""
    yield
    for event_name in _DYNAMIC_EVENTS:
        with contextlib.suppress(AttributeError):
            delattr(DatabaseRequiresEvents, event_name)
