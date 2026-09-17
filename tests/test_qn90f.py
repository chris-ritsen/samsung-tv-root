import subprocess
from pathlib import Path, PurePosixPath

import pytest

from samsung_tv_root.qn90f import (
    REMOTE_STAGING_DIRECTORY,
    RootExploitCompletion,
    RootSessionError,
    SdbExploitClient,
    SdbTransportError,
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
