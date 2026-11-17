#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
import time

from lightkube.core.client import Client
from lightkube.resources.core_v1 import Pod

try:
    from jubilant import Juju, all_active
except ImportError:
    from jubilant_backports import Juju, all_active

logger = logging.getLogger(__name__)

TEST_APP_NAME = "postgresql-test-app"


def run_command_on_unit(juju: Juju, unit_name: str, command: str) -> str:
    """Run a command on a specific unit.

    Args:
        juju: The Jubilant Juju instance for the model under test
        unit_name: The name of the unit to run the command on
        command: The command to run

    Returns:
        the command output if it succeeds, otherwise raises an exception.
    """
    return juju.exec(command, unit=unit_name).stdout


def get_machine_from_unit(juju: Juju, unit_name: str) -> str:
    """Get the name of the machine from a specific unit.

    Args:
        juju: The Jubilant Juju instance for the model under test
        unit_name: The name of the unit to get the machine

    Returns:
        The name of the machine.
    """
    raw_hostname = run_command_on_unit(juju, unit_name, "hostname")
    return raw_hostname.strip()


def restart_machine(juju: Juju, unit_name: str) -> None:
    """Restart the machine where a unit run on.

    Args:
        juju: The Jubilant Juju instance for the model under test
        unit_name: The name of the unit to restart the machine
    """
    raw_hostname = get_machine_from_unit(juju, unit_name)
    restart_machine_command = f"lxc restart {raw_hostname}"
    subprocess.check_call(restart_machine_command.split())


def smoke_base(juju: Juju, charm: str, base: str) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    logger.info("Deploy charms")
    is_k8s = juju.status().model.type == "caas"

    if is_k8s:
        postgresql = "postgresql-k8s"
        pgbouncer = "pgbouncer-k8s"
        pgb_units = 1
        pgb_base = "ubuntu@22.04"
    else:
        postgresql = "postgresql"
        pgbouncer = "pgbouncer"
        pgb_units = 0
        pgb_base = base
    if base == "ubuntu@22.04":
        pg_channel = "14/edge"
        pg_base = "ubuntu@22.04"
    else:
        pg_channel = "16/edge"
        pg_base = "ubuntu@24.04"
    # `juju deploy` runs in the background, so the deployments happen in parallel (like the
    # previous `asyncio.gather` of `model.deploy()` calls)
    juju.deploy(postgresql, channel=pg_channel, num_units=1, base=pg_base, trust=True)
    juju.deploy(pgbouncer, channel="1/edge", num_units=pgb_units, base=pgb_base, trust=True)
    juju.deploy(charm, app=TEST_APP_NAME, num_units=1, base=base)
    juju.integrate(postgresql, pgbouncer)
    juju.integrate(f"{TEST_APP_NAME}:database", pgbouncer)
    juju.wait(
        lambda status: all_active(status, postgresql, pgbouncer, TEST_APP_NAME),
        timeout=1000,
    )

    unit_name = f"{TEST_APP_NAME}/0"

    logger.info("Test continuous writes")
    juju.run(unit_name, "start-continuous-writes")

    time.sleep(10)

    logger.info("Show continuous writes")
    results = juju.run(unit_name, "show-continuous-writes")
    show_writes = int(results.results["writes"])

    time.sleep(10)

    results = juju.run(unit_name, "stop-continuous-writes")

    writes = int(results.results["writes"])
    assert writes > 0
    assert writes > show_writes

    params = {
        "dbname": f"{TEST_APP_NAME.replace('-', '_')}_database",
        "query": "SELECT COUNT(number), MAX(number) FROM continuous_writes;",
        "relation-name": "database",
        "readonly": False,
    }
    results = juju.run(unit_name, "run-sql", params=params)
    count, maximum = results.results["results"].strip("[]").split(", ")
    count = int(count)
    maximum = int(maximum)

    assert writes == count == maximum

    juju.run(unit_name, "clear-continuous-writes")


def restart_base(juju: Juju) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    is_k8s = juju.status().model.type == "caas"

    unit_name = f"{TEST_APP_NAME}/0"

    logger.info("Start continuous writes")
    juju.run(unit_name, "start-continuous-writes")

    time.sleep(10)

    results = juju.run(unit_name, "show-continuous-writes")
    early_writes = int(results.results["writes"])

    if is_k8s:
        logger.info("Deleting the pod")
        client = Client(namespace=juju.status().model.name)
        client.delete(Pod, name=f"{TEST_APP_NAME}-0")
    else:
        logger.info("Restarting lxc")
        restart_machine(juju, unit_name)

    logger.info("Wait for idle")
    juju.wait(lambda status: all_active(status, TEST_APP_NAME), timeout=600)

    logger.info("Check that writes are increasing")
    results = juju.run(unit_name, "show-continuous-writes")
    show_writes = int(results.results["writes"])

    time.sleep(10)

    results = juju.run(unit_name, "stop-continuous-writes")

    writes = int(results.results["writes"])
    assert writes > 0
    assert writes > show_writes > early_writes
