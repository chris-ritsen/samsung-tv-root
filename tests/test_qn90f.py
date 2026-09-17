import subprocess
import asyncio
from pathlib import Path, PurePosixPath

import pytest

from samsung_tv_root.qn90f import (
    REMOTE_STAGING_DIRECTORY,
    RootExploitCompletion,
    RootSessionError,
    SdbExploitClient,
    SdbTransportError,
    Qn90fRootSession,
    RootSessionConfig,
    TVDeviceProfile,
)


def completion_output() -> str:
    return "\n".join(
        (
            "probe=launch-root-agent",
            "pointer_size=4",
            "architecture=Arm",
            "physical_scan_pte_state=restored",
            "credential_write_reference_guard=pass",
            "credential_prewrite=pass",
            "credential_write=pass",
            "credential_write_readback=pass",
            "root_agent_exec=pass",
            "credential_restore_write=pass",
            "credential_restore_readback=pass",
            "physical_page_pte_state=restored",
            "root_task_action name=agent-launch result=pass",
            "credential_uid=901",
            "credential_gid=901",
            "root_agent_prelaunch tid=12 uid=0 euid=0 gid=0 egid=0",
            "credential_restored uid=901 euid=901 gid=901 egid=901",
        )
    )


def test_qn90f_completion_requires_restoration_evidence() -> None:
    result = subprocess.CompletedProcess(("sdb",), 0, "", "")
    completion = RootExploitCompletion.validate(result, completion_output())
    assert completion.sdk_uid == 901
    assert completion.sdk_gid == 901


def test_qn90f_completion_rejects_missing_pte_restoration() -> None:
    result = subprocess.CompletedProcess(("sdb",), 0, "", "")
    output = completion_output().replace("physical_page_pte_state=restored\n", "")
    with pytest.raises(RootSessionError, match="incomplete"):
        RootExploitCompletion.validate(result, output)


def test_qn90f_completion_rejects_wrong_managed_architecture() -> None:
    result = subprocess.CompletedProcess(("sdb",), 0, "", "")
    output = completion_output().replace("architecture=Arm", "architecture=Arm64")
    with pytest.raises(RootSessionError, match="architecture=Arm"):
        RootExploitCompletion.validate(result, output)


def test_qn90f_remote_paths_are_always_posix() -> None:
    assert isinstance(REMOTE_STAGING_DIRECTORY, PurePosixPath)
    assert str(REMOTE_STAGING_DIRECTORY / "payload.dll") == (
        "/home/owner/share/tmp/sdk_tools/qn90f-probe/payload.dll"
    )


def test_qn90f_push_rejects_sdb_error_with_zero_exit(monkeypatch) -> None:
    client = SdbExploitClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(
        ("sdb",),
        0,
        "pushed file 100%\n",
        "error: You cannot push files to this path.\n",
    )
    monkeypatch.setattr(client, "_run", lambda *args, **kwargs: result)

    with pytest.raises(SdbTransportError, match="cannot push files"):
        client.push(Path("probe"), REMOTE_STAGING_DIRECTORY / "probe")


def test_qn90f_interactive_session_uses_pty_shell(monkeypatch, tmp_path) -> None:
    identity = type(
        "Identity",
        (),
        {
            "pid": 1,
            "uid": 0,
            "euid": 0,
            "gid": 0,
            "egid": 0,
            "effective_capabilities": "3fffffffff",
            "smack_label": "User",
        },
    )()
    connection = type("Connection", (), {"identity": identity})()
    completion = type(
        "Completion",
        (),
        {"sdk_uid": 901, "sdk_gid": 901, "transport_returncode": 1},
    )()

    class Lease:
        remote_log_path = REMOTE_STAGING_DIRECTORY / "log"
        listener_host = "192.0.2.10"
        listener_port = 49152

        def __init__(self) -> None:
            self.connection = connection
            self.completion = completion
            self.shutdown_called = False
            self.close_called = False

        async def shutdown(self) -> None:
            self.shutdown_called = True

        async def close(self) -> None:
            self.close_called = True

    lease = Lease()
    config = RootSessionConfig(
        profile=TVDeviceProfile(),
        tv_host="192.0.2.50",
        callback_host="192.0.2.10",
        bind_host="192.0.2.10",
        listener_port=0,
        accept_timeout=30.0,
        command_timeout=45.0,
        payload_directory=tmp_path,
        shell_port=22333,
        shell_connect_timeout=12.5,
        payload_files=(),
    )
    session = Qn90fRootSession(config, object())
    monkeypatch.setattr(session.acquirer, "acquire", lambda: _async_value(lease))
    observed: dict[str, object] = {}

    class Shell:
        def __init__(self, shell_config) -> None:
            observed["config"] = shell_config

        async def run(self, shell_connection) -> int:
            observed["connection"] = shell_connection
            return 0

    monkeypatch.setattr("samsung_tv_root.qn90f.Qn90fRootShell", Shell)

    assert asyncio.run(session.run(None)) == 0
    shell_config = observed["config"]
    assert shell_config.tv_host == "192.0.2.50"
    assert shell_config.allowed_host == "192.0.2.10"
    assert shell_config.port == 22333
    assert shell_config.connect_timeout == 12.5
    assert observed["connection"] is connection
    assert lease.shutdown_called
    assert lease.close_called


async def _async_value(value):
    return value
