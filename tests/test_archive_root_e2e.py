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
            "Microsoft.NETCore.App 3.1.3 [/usr/share/dotnet/shared/Microsoft.NETCore.App]\n"
            "Microsoft.NETCore.App 6.0.0 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            "6.0",
        ),
        (None, "3.1"),
        (
            "Microsoft.NETCore.App 3.0.0 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            None,
        ),
        (
            "Microsoft.NETCore.App 3.2.0 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            None,
        ),
        (
            "Microsoft.NETCore.App 5.0.0 [/usr/share/dotnet/shared/Microsoft.NETCore.App]",
            None,
        ),
        ("", None),
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
                if runtimes is None:
                    return CaptureResult("Unknown option --list-runtimes.\n[exit:255]\n", 1)
                output = runtimes
            elif command == "readlink -f /usr/share/dotnet.tizen/netcoreapp":
                output = "/usr/share/dotnet/shared/Microsoft.NETCore.App/3.1.3"
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
        assert assessment.runtime_source == "detected"


@pytest.mark.parametrize("runtime", ("3.1", "6.0"))
def test_explicit_runtime_keeps_target_checks(runtime) -> None:
    from samsung_tv_root.archive_root import _check_target
    from samsung_tv_root.sdb import CaptureResult

    calls = []

    class Client:
        def connect(self):
            calls.append("connect")

        def require_device(self):
            calls.append("device")

        def require_shell_injection(self):
            calls.append("injection")

        def capture(self, command, timeout=15):
            calls.append(command)
            if command.startswith("getcap"):
                output = (
                    "/usr/bin/dotnet cap_setgid,cap_sys_admin=ei\n"
                    "/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip"
                )
            elif "tar --help" in command:
                output = "--to-command"
            else:
                assert command.startswith("sha256sum")
                output = "hashes"
            return CaptureResult(output + "\n[exit:0]\n", 0)

    assessment = _check_target(Client(), runtime)
    assert (assessment.runtime, assessment.runtime_source) == (runtime, "explicit")
    assert calls[:3] == ["connect", "device", "injection"]
    assert len(calls) == 6


@pytest.mark.parametrize("operation", ("probe", "root"))
def test_archive_cli_forwards_runtime_and_bridge(monkeypatch, operation) -> None:
    from samsung_tv_root import cli

    received = {}

    async def probe(host, **options):
        received.update(host=host, **options)
        return {"commands": []}

    monkeypatch.setattr(cli, "probe_archive_root", probe)
    argv = [
        "archive-root", operation, "192.0.2.77", "--runtime", "3.1",
        "--bridge-token", "ab" * 16, "--bridge-port", "26104",
    ]
    if operation == "root":
        argv.extend(("--command", "id"))
    arguments = cli.build_parser().parse_args(argv)
    assert arguments.handler(arguments) == 0
    assert received["host"] == "192.0.2.77"
    assert received["runtime"] == "3.1"
    assert received["bridge_token"] == "ab" * 16
    assert received["bridge_port"] == 26104
    if operation == "root":
        assert received["commands"] == ("id",)


@pytest.mark.parametrize(
    ("frozen", "platform", "original", "expected"),
    (
        (True, "linux", "/system", "/system"),
        (True, "linux", None, None),
        (False, "linux", "/system", "/bundle"),
        (True, "win32", "/system", "/bundle"),
    ),
)
def test_openssl_uses_host_libraries(monkeypatch, frozen, platform, original, expected):
    from samsung_tv_root import archive_root

    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle")
    if original is None:
        monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    else:
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", original)
    received = {}

    def run(command, **options):
        received.update(options)
        assert command == ("openssl", "version")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(archive_root.subprocess, "run", run)
    archive_root._openssl("version")
    assert received["env"].get("LD_LIBRARY_PATH") == expected
    assert os.environ["LD_LIBRARY_PATH"] == "/bundle"


def test_openssl_missing_binary_has_actionable_error(monkeypatch) -> None:
    from samsung_tv_root import archive_root

    def run(*args, **kwargs):
        raise FileNotFoundError("openssl")

    monkeypatch.setattr(archive_root.subprocess, "run", run)
    with pytest.raises(archive_root.ArchiveRootError, match="OpenSSL was not found"):
        archive_root._openssl("version")


@pytest.mark.parametrize(
    ("runtime_path", "readable"),
    (
        ("/usr/share/dotnet/shared/Microsoft.NETCore.App/3.0.0", True),
        ("/usr/share/dotnet.tizen/netcoreapp", True),
        ("/usr/share/dotnet/shared/Microsoft.NETCore.App/3.1.3", False),
    ),
)
def test_archive_route_rejects_unusable_active_runtime(runtime_path, readable) -> None:
    from samsung_tv_root.archive_root import ArchiveRootError, _runtime
    from samsung_tv_root.sdb import CaptureResult

    class Client:
        def capture(self, command, timeout=15):
            if "--list-runtimes" in command:
                return CaptureResult("Unknown option --list-runtimes.\n[exit:255]\n", 1)
            if command.startswith("readlink"):
                return CaptureResult(runtime_path + "\n[exit:0]\n", 0)
            return CaptureResult(f"\n[exit:{0 if readable else 1}]\n", 0)

    with pytest.raises(ArchiveRootError):
        _runtime(Client())


def test_archive_route_preserves_runtime_command_failure() -> None:
    from samsung_tv_root.archive_root import ArchiveRootError, _runtime
    from samsung_tv_root.sdb import CaptureResult

    class Client:
        def capture(self, command):
            assert command == "/usr/bin/dotnet --list-runtimes"
            return CaptureResult("Permission denied\n[exit:1]\n", 1)

    with pytest.raises(ArchiveRootError, match="Permission denied"):
        _runtime(Client())


@pytest.mark.parametrize("runtime", (None, "3.1", "6.0"))
@pytest.mark.parametrize(
    "capabilities",
    (
        "/usr/bin/dotnet cap_setgid=eip\n/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip",
        "/usr/bin/dotnet cap_setgid,cap_sys_admin=p\n/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=eip",
        "/usr/bin/dotnet cap_setgid,cap_sys_admin=ei\n/usr/sbin/sdbd-tarlauncher cap_setgid=p",
    ),
)
def test_archive_route_rejects_missing_effective_capabilities(capabilities, runtime) -> None:
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
        _check_target(Client(), runtime)


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
