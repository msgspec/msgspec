from mypy import api


def test_mypy(typing_examples_file):
    stdout, stderr, code = api.run([typing_examples_file])
    assert code == 0, f"mypy failed:\n{stdout}"
