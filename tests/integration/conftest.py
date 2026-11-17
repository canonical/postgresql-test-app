# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import pytest

try:
    from jubilant import Juju, temp_model
except ImportError:
    from jubilant_backports import Juju, temp_model

from . import architecture


def pytest_addoption(parser: pytest.Parser):
    """Add command line options (replacing those previously provided by pytest-operator)."""
    parser.addoption(
        "--controller",
        help="Juju controller to use for the tests.",
    )
    parser.addoption(
        "--model",
        help="Juju model to use for the tests; if not specified, a temporary model is created.",
    )
    parser.addoption(
        "--keep-models",
        action="store_true",
        help="Keep the temporary models created for the tests.",
    )


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    """Pytest fixture that wraps :func:`temp_model`.

    This adds command line parameters ``--controller``, ``--model`` and ``--keep-models``
    (see help for details).
    """
    controller = request.config.getoption("--controller")
    model = request.config.getoption("--model")
    keep_models = bool(request.config.getoption("--keep-models"))

    if model:
        if controller:
            model = f"{controller}:{model}"
        juju = Juju(model=model)
        yield juju
    else:
        with temp_model(keep=keep_models, controller=controller) as juju:
            yield juju


@pytest.fixture
def charm_jammy():
    # Return str instead of pathlib.Path since juju deploy (and Jubilant) expect local charms to
    # begin with `./` or `/` to distinguish them from Charmhub charms.
    return f"./postgresql-test-app_ubuntu@22.04-{architecture.architecture}.charm"


@pytest.fixture
def charm_noble():
    # Return str instead of pathlib.Path since juju deploy (and Jubilant) expect local charms to
    # begin with `./` or `/` to distinguish them from Charmhub charms.
    return f"./postgresql-test-app_ubuntu@24.04-{architecture.architecture}.charm"
