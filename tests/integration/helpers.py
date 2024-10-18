#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


async def run_command_on_unit(ops_test: OpsTest, unit_name: str, command: str) -> str:
    """Run a command on a specific unit.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit to run the command on
        command: The command to run

    Returns:
        the command output if it succeeds, otherwise raises an exception.
    """
    complete_command = ["exec", "--unit", unit_name, "--", *command.split()]
    return_code, stdout, _ = await ops_test.juju(*complete_command)
    if return_code != 0:
        logger.error(stdout)
        raise Exception(
            f"Expected command '{command}' to succeed instead it failed: {return_code}"
        )
    return stdout


async def get_machine_from_unit(ops_test: OpsTest, unit_name: str) -> str:
    """Get the name of the machine from a specific unit.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit to get the machine

    Returns:
        The name of the machine.
    """
    raw_hostname = await run_command_on_unit(ops_test, unit_name, "hostname")
    return raw_hostname.strip()


async def restart_machine(ops_test: OpsTest, unit_name: str) -> None:
    """Restart the machine where a unit run on.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit to restart the machine
    """
    raw_hostname = await get_machine_from_unit(ops_test, unit_name)
    restart_machine_command = f"lxc restart {raw_hostname}"
    subprocess.check_call(restart_machine_command.split())
