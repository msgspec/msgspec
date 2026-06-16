import pytest


# codspeed CI does not allow running a matrix, or submitting the same benchmarks twice
# under the same name (e.g. one run under arm, one under amd). easiest way around this
# was to use autoparametrisation to pretend the tests are different, and then select
# them in CI via '-k <arch>'.
@pytest.fixture(autouse=True, params=["amd", "arm"])
def provide_fake_arch(request):
    return request.param
