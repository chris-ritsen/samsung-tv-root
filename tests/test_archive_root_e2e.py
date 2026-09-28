"""Opt-in end-to-end checks for the SDK archive root route.

Failure cases to preserve: missing SDB foothold or capabilities; no supported
.NET runtime; failed namespace isolation or bind mounts; rejected archive
signature; launcher retaining SDK UID; missing or unauthenticated callback; and
incomplete staging cleanup. These checks must not be inferred from a successful
firmware/static inspection alone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_archive_route_accepts_an_unlisted_tv_without_a_model_name() -> None:
    from samsung_tv_root.cli import build_parser

    parser = build_parser()
    arguments = parser.parse_args(
        ["archive-root", "root", "192.0.2.77", "--command", "id"]
    )
    assert arguments.host == "192.0.2.77"
    assert arguments.model is None


@pytest.mark.parametrize(
    ("runtimes", "expected"),
    (
        (
            "Microsoft.NETCore.App 3.1.3 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            "3.1",
        ),
        (
            "Microsoft.NETCore.App 6.0.0 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            "6.0",
        ),
        (
            "Microsoft.NETCore.App 8.0.1 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            "6.0",
        ),
        (
            "Microsoft.AspNetCore.App 8.0.1 [/usr/share/dotnet/shared/Microsoft.AspNetCore.App]",
            None,
        ),
    ),
)
def test_archive_route_selects_payload_from_target_runtime(runtimes, expected) -> None:
    from samsung_tv_root.archive_root import ArchiveRootError, _check_target
    from samsung_tv_root.sdb import CaptureResult

    class Client:
        def connect(self):
            pass

        def require_device(self):
            pass

        def require_shell_injection(self):
            pass

        def capture(self, command, timeout=15):
            if command.startswith("getcap"):
                output = (
                    "/usr/bin/dotnet cap_setgid,cap_sys_admin=ei\n"
                    "/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip"
                )
            elif "--list-runtimes" in command:
                output = runtimes
            elif "tar --help" in command:
                output = "--to-command"
            else:
                output = "hash-passwd /etc/passwd\nhash-key /usr/share/sdbd/public.pem"
            return CaptureResult(output + "\n[exit:0]\n", 0.0)

    if expected is None:
        with pytest.raises(ArchiveRootError, match="runtime"):
            _check_target(Client())
    else:
        assessment = _check_target(Client())
        assert assessment.runtime == expected


@pytest.mark.parametrize(
    "capabilities",
    (
        "/usr/bin/dotnet cap_setgid=eip\n/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip",
        "/usr/bin/dotnet cap_setgid,cap_sys_admin=p\n/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip",
        "/usr/bin/dotnet cap_setgid,cap_sys_admin=ei\n/usr/sbin/sdbd-tarlauncher cap_setgid=p",
    ),
)
def test_archive_route_rejects_missing_effective_capabilities(capabilities) -> None:
    from samsung_tv_root.archive_root import ArchiveRootError, _check_target
    from samsung_tv_root.sdb import CaptureResult

    class Client:
        def connect(self):
            pass

        def require_device(self):
            pass

        def require_shell_injection(self):
            pass

        def capture(self, command, timeout=15):
            return CaptureResult(capabilities + "\n[exit:0]\n", 0.0)

    with pytest.raises(ArchiveRootError, match="capabilit"):
        _check_target(Client())


@pytest.mark.parametrize("model", ("qn90b", "qn90f"))
def test_archive_root_on_owner_tv(model: str) -> None:
    host = os.environ.get(f"SAMSUNG_TV_ARCHIVE_ROOT_{model.upper()}")
    evidence_dir = os.environ.get("SAMSUNG_TV_ARCHIVE_ROOT_EVIDENCE_DIR")
    if not host or not evidence_dir:
        pytest.skip("live TV host and evidence directory not configured")

    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "samsung_tv_root",
            "--output",
            "json",
            "archive-root",
            "probe",
            host,
        ),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    artifact = Path(evidence_dir) / f"{model}-archive-root.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "model": model,
                "host": host,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert result.returncode == 0, artifact
    evidence = json.loads(result.stdout)
    assert evidence["authenticated"] is True
    assert evidence["uid"] == 0
    assert evidence["euid"] == 0
    assert evidence["gid"] == 0
    assert evidence["egid"] == 0
    assert int(evidence["cap_eff"], 16) != 0
    assert evidence["system_files_unchanged"] is True
    assert evidence["staging_cleaned"] is True


@pytest.mark.parametrize("model", ("qn90b", "qn90f"))
def test_archive_root_command_on_owner_tv(model: str) -> None:
    host = os.environ.get(f"SAMSUNG_TV_ARCHIVE_ROOT_{model.upper()}")
    evidence_dir = os.environ.get("SAMSUNG_TV_ARCHIVE_ROOT_EVIDENCE_DIR")
    if not host or not evidence_dir:
        pytest.skip("live TV host and evidence directory not configured")

    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "samsung_tv_root",
            "--output",
            "json",
            "archive-root",
            "root",
            host,
            "--command",
            "id",
        ),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    artifact = Path(evidence_dir) / f"{model}-archive-root-command.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert result.returncode == 0, artifact
    evidence = json.loads(result.stdout)
    assert evidence["authenticated"] is True
    assert evidence["uid"] == 0
    assert len(evidence["commands"]) == 1
    command = evidence["commands"][0]
    assert command["command"] == "id"
    assert command["exit_code"] == 0
    assert command["timed_out"] is False
    assert "uid=0" in command["stdout"]
    assert command["stderr"] == ""
    assert evidence["system_files_unchanged"] is True
    assert evidence["staging_cleaned"] is True
