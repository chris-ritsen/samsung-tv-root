from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(
    path
    for directory in ("modules", "tools")
    for path in (ROOT / directory).rglob("*.sh")
)
BASH = shutil.which("bash")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_shell_script_uses_lf(script):
    assert b"\r" not in script.read_bytes(), "TV shell scripts require LF line endings"


@pytest.mark.skipif(BASH is None, reason="Bash is required for shell syntax checks")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_shell_script_parses(script):
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-n"],
        input=script.read_bytes(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
