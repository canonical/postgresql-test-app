#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from pytest_operator.plugin import OpsTest

from .helpers import restart_base, smoke_base

logger = logging.getLogger(__name__)

TEST_APP_NAME = "postgresql-test-app"


async def test_smoke(ops_test: OpsTest, charm_noble) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    await smoke_base(ops_test, charm_noble, "noble")


async def test_restart(ops_test: OpsTest) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    await restart_base(ops_test)
