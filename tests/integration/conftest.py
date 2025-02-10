import subprocess

import juju.model
import pytest

from . import architecture


@pytest.fixture(params=["lxd", "microk8s"], autouse=True)
async def cloud(request):
    controller = f"concierge-{request.param}"
    subprocess.run(["juju", "switch", controller], check=True)
    await juju.model.Controller().connect(controller)


@pytest.fixture
def charm():
    # Return str instead of pathlib.Path since python-libjuju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./postgresql-test-app_ubuntu@22.04-{architecture.architecture}.charm"
