import subprocess
import sys


def test_the_api_starts_without_the_simulation_packages(tmp_path):
    """The hosted API installs the project's dependencies only (pyproject: the `sim` group stays local). If anything
    the API imports at start-up needs numpy, pandas or pyarrow, every hosted request fails."""
    code = "import sys; sys.modules.update(numpy=None, pandas=None, pyarrow=None); import api.main"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={"PATH": "", "HEARTH_DB": str(tmp_path / "t.db"), "HEARTH_PASSWORD": ""})
    assert r.returncode == 0, r.stderr[-600:]
