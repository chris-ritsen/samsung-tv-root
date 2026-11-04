import pytest

from pathlib import Path

from samsung_tv_root.qn90b import (
    Qn90bError,
    Qn90bRootAcquirer,
    Qn90bRootEvidence,
    Qn90bRootExploit,
    Qn90bRootSessionConfig,
)
from samsung_tv_root.sdb import CaptureResult


PROBE_OUTPUT = (
    "uid=901(sdk) gid=901(sdk)\n"
    "SAMSUNG_TV_ROOT_KERNEL=5.4.77\n"
    "SAMSUNG_TV_ROOT_ARCHITECTURE=armv7l\n"
    "Tizen6.5/TV 6.5.0 (arm)\n"
    "BUILD_ID=T-PTMAKUC-REL-202310071804\n"
    "SAMSUNG_TV_ROOT_CAPABILITY_DOTNET=ready\n"
    "SAMSUNG_TV_ROOT_CAPABILITY_FDET_DEVICE=ready\n"
    "SAMSUNG_TV_ROOT_CAPABILITY_PONTUSM_LAYOUT=ready\n"
)


def make_exploit(monkeypatch, directory: Path, **kwargs) -> Qn90bRootExploit:
    monkeypatch.setattr("samsung_tv_root.qn90b.find_sdb", lambda: Path("sdb"))
    return Qn90bRootExploit("192.0.2.50", directory, **kwargs)


def stub_transport(monkeypatch, exploit: Qn90bRootExploit, runtime_output: str):
    monkeypatch.setattr(exploit.sdb, "connect", lambda: None)
    monkeypatch.setattr(exploit.sdb, "require_device", lambda: None)
    commands = []

    def capture(command: str, **kwargs) -> CaptureResult:
        commands.append(command)
        if command.startswith("readlink"):
            return CaptureResult(output=runtime_output, transport_returncode=1)
        return CaptureResult(output=PROBE_OUTPUT, transport_returncode=1)

    monkeypatch.setattr(exploit.sdb, "capture", capture)
    return commands


def test_preflight_selects_legacy_payloads_for_netcore31_runtime(
    monkeypatch, tmp_path: Path
) -> None:
    exploit = make_exploit(
        monkeypatch,
        tmp_path / "qn90b",
        legacy_payload_directory=tmp_path / "qn90b31",
    )
    stub_transport(
        monkeypatch,
        exploit,
        "/usr/share/dotnet/shared/Microsoft.NETCore.App/3.1.3\n\n[exit:0]\n",
    )

    exploit.preflight()

    assert exploit.payload_directory == (tmp_path / "qn90b31").resolve()


def test_preflight_keeps_default_payloads_for_net6_runtime(
    monkeypatch, tmp_path: Path
) -> None:
    exploit = make_exploit(
        monkeypatch,
        tmp_path / "qn90b",
        legacy_payload_directory=tmp_path / "qn90b31",
    )
    stub_transport(
        monkeypatch,
        exploit,
        "/usr/share/dotnet/shared/Microsoft.NETCore.App/6.0.9\n\n[exit:0]\n",
    )

    exploit.preflight()

    assert exploit.payload_directory == (tmp_path / "qn90b").resolve()


def test_preflight_keeps_default_payloads_when_runtime_is_unknown(
    monkeypatch, tmp_path: Path
) -> None:
    exploit = make_exploit(
        monkeypatch,
        tmp_path / "qn90b",
        legacy_payload_directory=tmp_path / "qn90b31",
    )
    stub_transport(
        monkeypatch,
        exploit,
        "readlink: /usr/share/dotnet.tizen/netcoreapp: No such file\n\n[exit:1]\n",
    )

    exploit.preflight()

    assert exploit.payload_directory == (tmp_path / "qn90b").resolve()


def test_acquirer_passes_legacy_payload_directory_to_exploit(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samsung_tv_root.qn90b.find_sdb", lambda: Path("sdb"))
    config = Qn90bRootSessionConfig(
        tv_host="192.0.2.50",
        callback_host="192.0.2.10",
        bind_host="192.0.2.10",
        listener_port=0,
        accept_timeout=1.0,
        command_timeout=1.0,
        payload_directory=tmp_path / "qn90b",
        legacy_payload_directory=tmp_path / "qn90b31",
    )
    acquirer = Qn90bRootAcquirer(config)

    assert acquirer.exploit.legacy_payload_directory == (
        tmp_path / "qn90b31"
    ).resolve()


def test_custom_payload_directory_skips_runtime_probe(
    monkeypatch, tmp_path: Path
) -> None:
    exploit = make_exploit(monkeypatch, tmp_path / "custom")
    commands = stub_transport(
        monkeypatch,
        exploit,
        "/usr/share/dotnet/shared/Microsoft.NETCore.App/3.1.3\n\n[exit:0]\n",
    )

    exploit.preflight()

    assert exploit.payload_directory == (tmp_path / "custom").resolve()
    assert not any(command.startswith("readlink") for command in commands)


def test_execute_reports_payload_output_when_identity_is_incomplete(
    monkeypatch, tmp_path: Path
) -> None:
    exploit = make_exploit(monkeypatch, tmp_path / "custom")
    output = (
        "Unhandled exception. System.IO.FileLoadException: Could not load file "
        "or assembly 'System.Runtime, Version=6.0.0.0'\n[exit:134]\n"
    )
    monkeypatch.setattr(
        exploit.sdb,
        "capture",
        lambda command, **kwargs: CaptureResult(
            output=output, transport_returncode=1
        ),
    )

    with pytest.raises(Qn90bError) as failure:
        exploit.execute("id")

    message = str(failure.value)
    assert "complete root identity" in message
    assert "FileLoadException" in message


def test_qn90b_root_evidence_accepts_complete_root_identity() -> None:
    Qn90bRootEvidence(
        "uid_after=0\n"
        "euid_after=0\n"
        "gid_after=0\n"
        "egid_after=0\n"
        "exec_begin\n"
    ).validate()


def test_qn90b_root_evidence_rejects_incomplete_identity() -> None:
    with pytest.raises(Qn90bError, match="complete root identity"):
        Qn90bRootEvidence("uid_after=0\neuid_after=0\nexec_begin\n").validate()


def test_qn90b_root_evidence_requires_exact_identity_markers() -> None:
    output = (
        "uid_after=00\n"
        "euid_after=0\n"
        "gid_after=0\n"
        "egid_after=0\n"
        "exec_begin\n"
    )
    with pytest.raises(Qn90bError, match="uid_after=0"):
        Qn90bRootEvidence(output).validate()
