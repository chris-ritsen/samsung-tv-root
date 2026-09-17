from pathlib import Path

import pytest

from samsung_tv_root import cli
from samsung_tv_root.sdb import CaptureResult


def test_preflight_parser_accepts_callback_overrides() -> None:
    arguments = cli.build_parser().parse_args(
        [
            "preflight",
            "qn90f",
            "192.0.2.50",
            "--callback-host",
            "192.0.2.10",
            "--bind-host",
            "0.0.0.0",
            "--port",
            "49152",
        ]
    )

    assert arguments.callback_host == "192.0.2.10"
    assert arguments.bind_host == "0.0.0.0"
    assert arguments.port == 49152


def test_qn90f_root_can_explicitly_skip_preflight(monkeypatch, capsys) -> None:
    arguments = cli.build_parser().parse_args(
        ["qn90f", "root", "192.0.2.50", "--skip-preflight", "--command", "id"]
    )
    called: dict[str, object] = {}

    def reject_preflight(*args, **kwargs):
        raise AssertionError("preflight must not run")

    def run_root_session(*args, **kwargs):
        called["host"] = args[1]
        called["commands"] = kwargs["commands"]
        return 0

    monkeypatch.setattr(cli, "preflight_qn90f", reject_preflight)
    monkeypatch.setattr(cli, "run_root_session", run_root_session)

    assert arguments.handler(arguments) == 0
    assert called == {"host": "192.0.2.50", "commands": ["id"]}
    assert "Preflight: skipped" in capsys.readouterr().err


def test_qn90f_root_runs_preflight_by_default(monkeypatch) -> None:
    arguments = cli.build_parser().parse_args(
        [
            "qn90f",
            "root",
            "192.0.2.50",
            "--port",
            "49152",
            "--command",
            "id",
        ]
    )
    assessment = object()
    observed: dict[str, object] = {}

    def preflight(*args, **kwargs):
        observed["preflight"] = (args, kwargs)
        return assessment

    monkeypatch.setattr(cli, "preflight_qn90f", preflight)
    monkeypatch.setattr(
        cli,
        "print_assessment",
        lambda value: observed.setdefault("assessment", value),
    )
    monkeypatch.setattr(cli, "run_root_session", lambda *args, **kwargs: 0)

    assert arguments.handler(arguments) == 0
    assert observed["assessment"] is assessment
    assert observed["preflight"] == (
        ("192.0.2.50", 15.0),
        {"callback_host": None, "bind_host": None, "port": 49152},
    )


def test_qn90f_preflight_rejects_empty_callback_output(monkeypatch) -> None:
    class Client:
        def __init__(self, executable: Path, host: str, *, timeout: float) -> None:
            pass

        def connect(self) -> None:
            pass

        def require_device(self) -> None:
            pass

        def require_shell_injection(self) -> None:
            pass

        def capture(self, *args, **kwargs) -> CaptureResult:
            return CaptureResult(output="", transport_returncode=1)

    monkeypatch.setattr(cli, "find_sdb", lambda: Path("sdb"))
    monkeypatch.setattr(cli, "SdbClient", Client)

    with pytest.raises(cli.CommandError, match="connected but returned no output"):
        cli.preflight_qn90f("192.0.2.50", 1.0)
