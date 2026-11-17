#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


try:
    from jubilant import Juju
except ImportError:
    from jubilant_backports import Juju

from .helpers import restart_base, smoke_base


def test_smoke(juju: Juju, charm_jammy) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    smoke_base(juju, charm_jammy, "ubuntu@22.04")


def test_restart(juju: Juju) -> None:
    """Verify that the charm works with latest Postgresql and Pgbouncer."""
    restart_base(juju)
