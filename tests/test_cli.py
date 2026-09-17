import os
from pathlib import Path

import pytest

from samsung_tv_root import cli
from samsung_tv_root.sdb import CaptureResult


def qn90f_uep_output(*lines: str, mode: str = "disable-uep") -> str:
    return "\n".join(
        (
            f"probe={mode}",
            "uep_status_validation=pass",
            *lines,
            "physical_page_pte_state=restored",
            "[exit:0]",
        )
    )


def write_profiles(path: Path, *profiles: tuple[str, str, str]) -> None:
    sections = ["version = 1", ""]
    for name, model, host in profiles:
        sections.extend(
            (
                f"[televisions.{name}]",
                f'model = "{model}"',
                f'host = "{host}"',
                "",
            )
        )
    path.write_text("\n".join(sections), encoding="utf-8")


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


def test_qn90f_root_parser_allows_configured_target() -> None:
    arguments = cli.build_parser().parse_args(["qn90f", "root"])

    assert arguments.host is None
    assert arguments.profile is None


def test_direct_target_infers_only_matching_model(tmp_path, capsys) -> None:
    config = tmp_path / "config.toml"
    write_profiles(
        config,
        ("bedroom", "qn90b", "192.0.2.40"),
        ("living-room", "qn90f", "192.0.2.50"),
    )
    arguments = cli.build_parser().parse_args(
        ["--config", str(config), "qn90f", "root"]
    )

    cli.resolve_direct_target(arguments, "qn90f")

    assert arguments.host == "192.0.2.50"
    assert "profile=living-room" in capsys.readouterr().err


def test_direct_target_applies_configured_relative_sdb(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """version = 1
sdb = "tools/sdb"

[televisions.living-room]
model = "qn90f"
host = "192.0.2.50"
""",
        encoding="utf-8",
    )
    arguments = cli.build_parser().parse_args(
        ["--config", str(config), "qn90f", "root"]
    )
    monkeypatch.delenv("SDB", raising=False)

    cli.resolve_direct_target(arguments, "qn90f")

    assert Path(os.environ["SDB"]) == tmp_path / "tools" / "sdb"


def test_direct_target_selects_named_profile(tmp_path) -> None:
    config = tmp_path / "config.toml"
    write_profiles(
        config,
        ("living-room", "qn90f", "192.0.2.50"),
        ("office", "qn90f", "192.0.2.51"),
    )
    arguments = cli.build_parser().parse_args(
        [
            "--config",
            str(config),
            "qn90f",
            "root",
            "--profile",
            "office",
        ]
    )

    cli.resolve_direct_target(arguments, "qn90f")

    assert arguments.host == "192.0.2.51"


def test_direct_target_requires_profile_when_model_is_ambiguous(tmp_path) -> None:
    config = tmp_path / "config.toml"
    write_profiles(
        config,
        ("living-room", "qn90f", "192.0.2.50"),
        ("office", "qn90f", "192.0.2.51"),
    )
    arguments = cli.build_parser().parse_args(
        ["--config", str(config), "qn90f", "root"]
    )

    with pytest.raises(cli.CommandError, match="multiple qn90f profiles"):
        cli.resolve_direct_target(arguments, "qn90f")


def test_direct_target_rejects_wrong_model_and_explicit_host(tmp_path) -> None:
    config = tmp_path / "config.toml"
    write_profiles(config, ("bedroom", "qn90b", "192.0.2.40"))
    wrong_model = cli.build_parser().parse_args(
        [
            "--config",
            str(config),
            "qn90f",
            "root",
            "--profile",
            "bedroom",
        ]
    )
    explicit_host = cli.build_parser().parse_args(
        ["qn90f", "root", "192.0.2.50", "--profile", "living-room"]
    )

    with pytest.raises(cli.CommandError, match="uses model qn90b"):
        cli.resolve_direct_target(wrong_model, "qn90f")
    with pytest.raises(cli.CommandError, match="either HOST or --profile"):
        cli.resolve_direct_target(explicit_host, "qn90f")


def test_uep_action_can_be_used_without_host() -> None:
    arguments = cli.build_parser().parse_args(["qn90f", "uep", "disable"])

    cli.normalize_uep_arguments(arguments)

    assert arguments.host is None
    assert arguments.action == "disable"


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


def test_qn90f_root_passes_interactive_shell_options(monkeypatch) -> None:
    arguments = cli.build_parser().parse_args(
        [
            "qn90f",
            "root",
            "192.0.2.50",
            "--skip-preflight",
            "--shell-port",
            "22333",
            "--shell-connect-timeout",
            "12.5",
        ]
    )
    observed: dict[str, object] = {}

    def run_root_session(*args, **kwargs):
        observed.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run_root_session", run_root_session)

    assert arguments.handler(arguments) == 0
    assert observed["commands"] is None
    assert observed["shell_port"] == 22333
    assert observed["shell_connect_timeout"] == 12.5


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


@pytest.mark.parametrize(
    "output",
    (
        qn90f_uep_output(
            "uep_status_before=1",
            "uep_status_write_observed=0",
            "uep_status_after=0",
            "uep_status_action=disabled",
        ),
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_action=already-disabled",
        ),
    ),
)
def test_qn90f_uep_disable_accepts_fresh_and_existing_zero(output: str) -> None:
    cli.require_qn90f_uep_result(output, disable=True)


@pytest.mark.parametrize(
    "output",
    (
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_action=inspect-only",
        ),
        qn90f_uep_output(
            "uep_status_before=1",
            "uep_status_action=already-disabled",
        ),
        qn90f_uep_output(
            "uep_status_before=1",
            "uep_status_after=0",
            "uep_status_action=disabled",
        ),
        "uep_status_before=0\nuep_status_action=already-disabled",
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_before=0",
            "uep_status_action=already-disabled",
        ),
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_action=already-disabled",
        ).replace("[exit:0]", "[exit:1]"),
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_action=already-disabled",
        )
        + "\n[exit:0]",
    ),
)
def test_qn90f_uep_disable_rejects_incomplete_evidence(output: str) -> None:
    with pytest.raises(cli.CommandError, match="UEP"):
        cli.require_qn90f_uep_result(output, disable=True)


def test_qn90f_uep_status_accepts_inspection_evidence() -> None:
    cli.require_qn90f_uep_result(
        qn90f_uep_output(
            "uep_status_before=0",
            "uep_status_action=inspect-only",
            mode="inspect-uep",
        ),
        disable=False,
    )
