#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import time

from juju.relation import Relation
from lightkube.core.client import Client
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from .helpers import restart_machine

logger = logging.getLogger(__name__)

TEST_APP_NAME = "postgresql-test-app"


async def integrate(ops_test: OpsTest, relation1: str, relation2: str) -> Relation:
    if hasattr(ops_test.model, "integrate"):
        return await ops_test.model.integrate(relation1, relation2)
    else:
        return await ops_test.model.relate(relation1, relation2)


async def test_smoke(ops_test: OpsTest, charm) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    logger.info("Deploy charms")
    is_k8s = ops_test.model.info.provider_type == "kubernetes"

    if is_k8s:
        postgresql = "postgresql-k8s"
        pgbouncer = "pgbouncer-k8s"
        pgb_units = 1
    else:
        postgresql = "postgresql"
        pgbouncer = "pgbouncer"
        pgb_units = 0
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
            charm,
            application_name=TEST_APP_NAME,
            num_units=1,
            series="jammy",
        ),
    )
    await integrate(ops_test, postgresql, pgbouncer)
    await integrate(ops_test, f"{TEST_APP_NAME}:database", pgbouncer)
    await ops_test.model.wait_for_idle(
        apps=[postgresql, pgbouncer, TEST_APP_NAME], status="active", timeout=1000, idle_period=30
    )

    logger.info("Test continuous writes")
    await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("start-continuous-writes")
    ).wait()

    time.sleep(10)

    logger.info("Show continuous writes")
    results = await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("show-continuous-writes")
    ).wait()
    show_writes = int(results.results["writes"])

    time.sleep(10)

    results = await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("stop-continuous-writes")
    ).wait()

    writes = int(results.results["writes"])
    assert writes > 0
    assert writes > show_writes

    params = {
        "dbname": f"{TEST_APP_NAME.replace('-', '_')}_database",
        "query": "SELECT COUNT(number), MAX(number) FROM continuous_writes;",
        "relation-name": "database",
        "readonly": False,
    }
    results = await (
        await ops_test.model.applications[TEST_APP_NAME].units[0].run_action("run-sql", **params)
    ).wait()
    count, maximum = results.results["results"].strip("[]").split(", ")
    count = int(count)
    maximum = int(maximum)

    assert writes == count == maximum

    await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("clear-continuous-writes")
    ).wait()


async def test_restart(ops_test: OpsTest) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    is_k8s = ops_test.model.info.provider_type == "kubernetes"

    logger.info("Start continuous writes")
    await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("start-continuous-writes")
    ).wait()

    time.sleep(10)

    results = await (
        await ops_test.model.applications[TEST_APP_NAME]
        .units[0]
        .run_action("show-continuous-writes")
    ).wait()
    early_writes = int(results.results["writes"])

    if is_k8s:
        logger.info("Deleting the pod")
        client = Client(namespace=ops_test.model.info.name)
        client.delete(Pod, name=f"{TEST_APP_NAME}-0")
    else:
        logger.info("Restarting lxc")
        await restart_machine(ops_test, ops_test.model.applications[TEST_APP_NAME].units[0].name)

    logger.info("Wait for idle")
    await ops_test.model.wait_for_idle(
        apps=[TEST_APP_NAME], status="active", timeout=600, idle_period=30
    )

    logger.info("Check that writes are increasing")
    for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True):
        with attempt:
            results = await (
                await ops_test.model.applications[TEST_APP_NAME]
                .units[0]
                .run_action("show-continuous-writes")
            ).wait()
            show_writes = int(results.results["writes"])

            time.sleep(10)

            results = await (
                await ops_test.model.applications[TEST_APP_NAME]
                .units[0]
                .run_action("stop-continuous-writes")
            ).wait()

    writes = int(results.results["writes"])
    assert writes > 0
    assert writes > show_writes > early_writes
