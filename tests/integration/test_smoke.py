#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time

import psycopg2
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

TEST_APP_NAME = "postgresql-test-app"


async def test_smoke(ops_test: OpsTest):
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    logger.info("Deploy charms")
    if ops_test.cloud_name == "localhost":
        postgresql = "postgresql"
        pgbouncer = "pgbouncer"
        pgb_units = 0
    else:
        postgresql = "postgresql-k8s"
        pgbouncer = "pgbouncer-k8s"
        pgb_units = 1
    await asyncio.gather(
        ops_test.model.deploy(
            postgresql,
            channel="14/edge",
            num_units=1,
            series="jammy",
            trust=True,
        ),
        ops_test.model.deploy(
            pgbouncer,
            channel="1/edge",
            num_units=pgb_units,
            series="jammy",
            trust=True,
        ),
        ops_test.model.deploy(
            await ops_test.build_charm("."),
            application_name=TEST_APP_NAME,
            num_units=1,
            series="jammy",
        ),
    )
    await ops_test.model.integrate(postgresql, pgbouncer)
    await ops_test.model.integrate(f"{TEST_APP_NAME}:first-database", pgbouncer)
    await ops_test.model.wait_for_idle(
        apps=[postgresql, pgbouncer, TEST_APP_NAME],
        status="active",
    )

    logger.info("Test continuous writes")
    await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("start-continuous-writes")
    ).wait()

    time.sleep(10)

    results = await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("stop-continuous-writes")
    ).wait()

    writes = int(results.results["writes"])
    assert writes > 0

    result = await (
        await ops_test.model.applications[postgresql].units[0].run_action("get-password")
    ).wait()
    password = result.results["password"]

    ip = await ops_test.model.applications[postgresql].units[0].get_public_address()

    connection_string = (
        f"dbname='{TEST_APP_NAME.replace('-', '_')}_first_database' user='operator'"
        f" host='{ip}' password='{password}' connect_timeout=10"
    )

    with psycopg2.connect(connection_string) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(number), MAX(number) FROM continuous_writes;")
        results = cursor.fetchone()
        count = results[0]
        maximum = results[1]
    connection.close()

    assert writes == count
    assert writes == maximum
