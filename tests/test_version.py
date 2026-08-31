from pathlib import Path
import tomllib

import pytest

import semaphore_ui
from semaphore_ui import cli


def test_cli_and_package_versions_match_pyproject(capsys):
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    declared_version = tomllib.loads(pyproject_path.read_text())["project"]["version"]

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"semaphore-ui {declared_version}"
    assert semaphore_ui.__version__ == declared_version
