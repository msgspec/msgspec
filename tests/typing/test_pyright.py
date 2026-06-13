import subprocess

import pyright


def test_pyright(typing_examples_file):
    result = pyright.run(typing_examples_file, stdout=subprocess.PIPE)
    assert result.returncode == 0, f"pyright failed:\n{result.stdout.decode()}"
