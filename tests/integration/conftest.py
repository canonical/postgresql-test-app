import subprocess

import pytest

from . import architecture


@pytest.fixture(params=["lxd", "microk8s"], autouse=True)
def cloud(request):
    subprocess.run(["juju", "switch", request.param], check=True)


@pytest.fixture
def charm():
    # Return str instead of pathlib.Path since python-libjuju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./postgresql-test-app_ubuntu@22.04-{architecture.architecture}.charm"
