from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import sys
from pathlib import Path

from . import __version__
from .compatibility import QN90F_PROFILE, TargetAssessment, TargetCompatibilityError
from .capabilities import CapabilityError
from .config import (
    ConfigurationError,
    configuration_template,
    default_configuration_path,
    load_configuration,
)
from .controller import (
    ControllerError,
    add_serve_arguments,
    default_control_file,
    send_control_request,
    serve,
    stream_control_events,
)
from .daemon import DaemonError, SamsungTvRootDaemon
from .doctor import inspect_installation, print_report
from .qn90b import Qn90bError, Qn90bRootExploit
from .qn90f import (
    DEFAULT_PAYLOAD_DIRECTORY as QN90F_PAYLOAD_DIRECTORY,
    RootAgentError,
    TVDeviceProfile,
    run_root_session,
)
from .sdb import SdbClient, SdbError, find_sdb
from .resources import payload_directory
from .service import (
    ServiceError,
    install_user_service,
    service_state,
    uninstall_user_service,
)


QN90B_PAYLOAD_DIRECTORY = payload_directory("qn90b")
QN90F_REMOTE_DIRECTORY = Path("/home/owner/share/tmp/sdk_tools/samsung-tv-root/qn90f")


class CommandError(RuntimeError):
    pass


def command_doctor(arguments: argparse.Namespace) -> int:
    print_report(
        inspect_installation(),
        json_output=arguments.json or arguments.output == "json",
    )
    return 0


def emit(value: object, output: str) -> None:
    if output == "json":
        print(json.dumps(value, indent=2, sort_keys=True))
        return
    for line in render_human(value):
        print(line)


def render_human(value: object, indentation: int = 0) -> list[str]:
    prefix = " " * indentation
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = str(key).replace("_", " ")
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{label}:")
                lines.extend(render_human(item, indentation + 2))
            else:
                lines.append(f"{prefix}{label}: {_human_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            rendered = render_human(item, indentation + 2)
            if not rendered:
                lines.append(f"{prefix}-")
                continue
            first = rendered[0].lstrip()
            lines.append(f"{prefix}- {first}")
            lines.extend(rendered[1:])
        return lines
    return [f"{prefix}{_human_scalar(value)}"]


def _human_scalar(value: object) -> str:
    if value is None:
        return "none"
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def command_configuration(arguments: argparse.Namespace) -> int:
    path = arguments.config.expanduser().resolve()
    if arguments.configuration_command == "init":
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(configuration_template())
        except FileExistsError as error:
            raise CommandError(f"configuration already exists: {path}") from error
        emit({"configuration": str(path), "created": True}, arguments.output)
        return 0
    configuration = load_configuration(path)
    emit(
        {
            "configuration": str(path),
            "televisions": [
                {
                    "name": television.name,
                    "model": television.model,
                    "host": television.host,
                    "root_on_presence": television.root_on_presence,
                    "remote_enabled": television.remote.enabled,
                    "remote_rules": len(television.remote.rules),
                }
                for television in configuration.televisions
            ],
        },
        arguments.output,
    )
    return 0


def command_daemon(arguments: argparse.Namespace) -> int:
    configuration = load_configuration(arguments.config.expanduser().resolve())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(
        SamsungTvRootDaemon(
            configuration,
            arguments.control_file.expanduser().resolve(),
        ).run()
    )
    return 0


def command_service(arguments: argparse.Namespace) -> int:
    if arguments.service_command == "install":
        state = install_user_service(
            arguments.config,
            arguments.executable,
            enable=arguments.enable,
            start=arguments.now,
        )
    elif arguments.service_command == "uninstall":
        state = uninstall_user_service(stop=arguments.now)
    else:
        state = service_state()
    emit(state.to_dict(), arguments.output)
    return 0


def command_controller_request(arguments: argparse.Namespace) -> int:
    request: dict[str, object] = {"action": arguments.controller_action}
    if getattr(arguments, "television", None) is not None:
        request["television"] = arguments.television
    if arguments.controller_action == "execute":
        request["command"] = arguments.tv_command
        request["timeout"] = arguments.command_timeout
    if getattr(arguments, "source", None) is not None:
        request["source"] = arguments.source
    if arguments.controller_action == "local_dimming.set":
        request["enabled"] = arguments.state == "enabled"
    response = asyncio.run(
        send_control_request(
            arguments.control_file.expanduser().resolve(),
            request,
            timeout=arguments.timeout,
        )
    )
    response.pop("ok", None)
    emit(response, arguments.output)
    return 0


def command_remote_events(arguments: argparse.Namespace) -> int:
    async def stream() -> None:
        topic = f"television.{arguments.television}.remote"
        async for event in stream_control_events(
            arguments.control_file.expanduser().resolve(),
            (topic,),
            arguments.timeout,
        ):
            emit(event, arguments.output)

    asyncio.run(stream())
    return 0


def preflight_qn90f(host: str, timeout: float) -> TargetAssessment:
    client = SdbClient(find_sdb(), host, timeout=timeout)
    client.connect()
    result = client.capture(
        QN90F_PROFILE.probe_command(),
        timeout=max(timeout, 20.0),
    )
    assessment = QN90F_PROFILE.assess(result.output)
    try:
        return assessment.require_compatible()
    except TargetCompatibilityError as error:
        raise CommandError(str(error)) from error


def print_assessment(assessment: TargetAssessment) -> None:
    print(assessment.render())


def qn90b_exploit(
    arguments: argparse.Namespace,
    *,
    require_tested: bool = False,
) -> Qn90bRootExploit:
    exploit = Qn90bRootExploit(
        arguments.host,
        arguments.payload_directory,
        sdb_timeout=arguments.sdb_timeout,
    )
    print_assessment(exploit.preflight(require_tested=require_tested))
    exploit.stage()
    return exploit


def command_preflight(arguments: argparse.Namespace) -> int:
    if arguments.tv == "qn90b":
        exploit = Qn90bRootExploit(
            arguments.host,
            QN90B_PAYLOAD_DIRECTORY,
            sdb_timeout=arguments.sdb_timeout,
        )
        assessment = exploit.preflight()
    else:
        assessment = preflight_qn90f(arguments.host, arguments.sdb_timeout)
    print_assessment(assessment)
    return 0


def command_qn90b_root(arguments: argparse.Namespace) -> int:
    exploit = qn90b_exploit(arguments)
    if arguments.command:
        result = exploit.execute(arguments.command, timeout=arguments.command_timeout)
        print(result.output, end="" if result.output.endswith("\n") else "\n")
        return 0
    exploit.shell(timeout=arguments.command_timeout)
    return 0


def command_qn90b_uep(arguments: argparse.Namespace) -> int:
    exploit = qn90b_exploit(arguments, require_tested=True)
    result = (
        exploit.disable_uep()
        if arguments.action == "disable"
        else exploit.read_uep_gate()
    )
    print(result.output, end="" if result.output.endswith("\n") else "\n")
    return 0


def command_qn90f_root(arguments: argparse.Namespace) -> int:
    print_assessment(preflight_qn90f(arguments.host, arguments.sdb_timeout))
    return run_root_session(
        TVDeviceProfile(),
        arguments.host,
        callback_host=arguments.callback_host,
        bind_host=arguments.bind_host,
        listener_port=arguments.port,
        accept_timeout=arguments.accept_timeout,
        command_timeout=arguments.command_timeout,
        sdb_timeout=arguments.sdb_timeout,
        payload_directory=arguments.payload_directory,
        commands=arguments.command,
    )


def command_qn90f_uep(arguments: argparse.Namespace) -> int:
    print_assessment(preflight_qn90f(arguments.host, arguments.sdb_timeout))
    payload = arguments.payload_directory / "MaliPhysicalProbe.dll"
    runtime = arguments.payload_directory / "MaliPhysicalProbe.runtimeconfig.json"
    missing = tuple(path.name for path in (payload, runtime) if not path.is_file())
    if missing:
        raise CommandError(
            "missing built QN90F payloads: "
            + ", ".join(missing)
            + "; run make payloads"
        )
    client = SdbClient(find_sdb(), arguments.host, timeout=arguments.sdb_timeout)
    client.connect()
    result = client.inject(f"/bin/mkdir -p {QN90F_REMOTE_DIRECTORY}")
    if result.returncode not in (0, 1):
        raise CommandError("failed to create the QN90F staging directory")
    remote_payload = QN90F_REMOTE_DIRECTORY / payload.name
    remote_runtime = QN90F_REMOTE_DIRECTORY / runtime.name
    client.push(payload, remote_payload)
    client.push(runtime, remote_runtime)
    mode = "disable-uep" if arguments.action == "disable" else "inspect-uep"
    invocation = shlex.join(("/usr/bin/dotnet", str(remote_payload), mode))
    output = client.capture(invocation, timeout=arguments.command_timeout).output
    if "uep_status_validation=pass" not in output:
        raise CommandError("QN90F UEP neighborhood validation did not pass")
    if mode == "disable-uep" and "uep_status_action=disabled" not in output:
        raise CommandError("QN90F UEP disable transition was not confirmed")
    print(output, end="" if output.endswith("\n") else "\n")
    return 0


def command_qn90f_serve(arguments: argparse.Namespace) -> int:
    print_assessment(preflight_qn90f(arguments.host, arguments.sdb_timeout))
    return asyncio.run(serve(arguments))


def add_transport_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("host")
    parser.add_argument("--sdb-timeout", type=float, default=15.0)


def add_root_options(
    parser: argparse.ArgumentParser,
    default_payload_directory: Path,
) -> None:
    add_transport_options(parser)
    parser.add_argument(
        "--payload-directory",
        type=Path,
        default=default_payload_directory,
    )
    parser.add_argument("--command-timeout", type=float, default=45.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Owner-authorized Samsung QN90B/QN90F root research"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--output",
        "-o",
        choices=("human", "json"),
        default="human",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_configuration_path(),
    )
    parser.add_argument(
        "--control-file",
        type=Path,
        default=default_control_file(),
    )
    parser.add_argument(
        "--sdb",
        type=Path,
        help="path to Tizen Studio's sdb executable",
    )
    commands = parser.add_subparsers(dest="command_name", required=True)

    doctor = commands.add_parser("doctor", help="check this host installation")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    configuration = commands.add_parser("config")
    configuration_commands = configuration.add_subparsers(
        dest="configuration_command",
        required=True,
    )
    configuration_commands.add_parser("init").set_defaults(
        handler=command_configuration
    )
    configuration_commands.add_parser("check").set_defaults(
        handler=command_configuration
    )

    daemon = commands.add_parser("daemon")
    daemon_commands = daemon.add_subparsers(dest="daemon_command", required=True)
    daemon_commands.add_parser("run").set_defaults(handler=command_daemon)

    service = commands.add_parser("service")
    service_commands = service.add_subparsers(dest="service_command", required=True)
    service_install = service_commands.add_parser("install")
    service_install.add_argument("--executable", type=Path)
    service_install.add_argument("--enable", action="store_true")
    service_install.add_argument("--now", action="store_true")
    service_install.set_defaults(handler=command_service)
    service_uninstall = service_commands.add_parser("uninstall")
    service_uninstall.add_argument("--now", action="store_true")
    service_uninstall.set_defaults(handler=command_service)
    service_commands.add_parser("status").set_defaults(handler=command_service)

    status_command = commands.add_parser("status")
    status_command.add_argument("--timeout", type=float, default=10.0)
    status_command.set_defaults(
        handler=command_controller_request,
        controller_action="status",
    )

    capabilities = commands.add_parser("capabilities")
    capabilities.add_argument("television")
    capabilities.add_argument("--timeout", type=float, default=10.0)
    capabilities.set_defaults(
        handler=command_controller_request,
        controller_action="capabilities",
    )

    root = commands.add_parser("root")
    root_commands = root.add_subparsers(dest="root_command", required=True)
    root_acquire = root_commands.add_parser("acquire")
    root_acquire.add_argument("television")
    root_acquire.add_argument("--timeout", type=float, default=45.0)
    root_acquire.set_defaults(
        handler=command_controller_request,
        controller_action="root.acquire",
    )

    execute = commands.add_parser("execute")
    execute.add_argument("television")
    execute.add_argument("tv_command")
    execute.add_argument("--timeout", type=float, default=20.0)
    execute.add_argument("--command-timeout", type=float, default=15.0)
    execute.set_defaults(
        handler=command_controller_request,
        controller_action="execute",
    )

    source = commands.add_parser("source")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    for name, action in (
        ("list", "source.list"),
        ("current", "source.current"),
        ("recover", "source.recover"),
    ):
        command = source_commands.add_parser(name)
        command.add_argument("television")
        command.add_argument("--timeout", type=float, default=20.0)
        command.set_defaults(
            handler=command_controller_request,
            controller_action=action,
        )
    source_select = source_commands.add_parser("select")
    source_select.add_argument("television")
    source_select.add_argument("source", choices=("HDMI1", "HDMI2", "HDMI3", "HDMI4"))
    source_select.add_argument("--timeout", type=float, default=20.0)
    source_select.set_defaults(
        handler=command_controller_request,
        controller_action="source.select",
    )

    hdmi_policy = commands.add_parser("hdmi-policy")
    hdmi_policy_commands = hdmi_policy.add_subparsers(
        dest="hdmi_policy_command",
        required=True,
    )
    for name, action in (
        ("status", "hdmi_policy.status"),
        ("enforce", "hdmi_policy.enforce"),
    ):
        command = hdmi_policy_commands.add_parser(name)
        command.add_argument("television")
        command.add_argument(
            "--source",
            choices=("HDMI1", "HDMI2", "HDMI3", "HDMI4"),
        )
        command.add_argument("--timeout", type=float, default=20.0)
        command.set_defaults(
            handler=command_controller_request,
            controller_action=action,
        )

    local_dimming = commands.add_parser("local-dimming")
    local_dimming_commands = local_dimming.add_subparsers(
        dest="local_dimming_command",
        required=True,
    )
    for name, action in (
        ("status", "local_dimming.status"),
        ("toggle", "local_dimming.toggle"),
    ):
        command = local_dimming_commands.add_parser(name)
        command.add_argument("television")
        command.add_argument("--timeout", type=float, default=20.0)
        command.set_defaults(
            handler=command_controller_request,
            controller_action=action,
        )
    local_dimming_set = local_dimming_commands.add_parser("set")
    local_dimming_set.add_argument("television")
    local_dimming_set.add_argument("state", choices=("enabled", "disabled"))
    local_dimming_set.add_argument("--timeout", type=float, default=20.0)
    local_dimming_set.set_defaults(
        handler=command_controller_request,
        controller_action="local_dimming.set",
    )

    display = commands.add_parser("display")
    display_commands = display.add_subparsers(dest="display_command", required=True)
    for name, action in (
        ("status", "display.status"),
        ("picture-off", "display.picture_off"),
        ("wake", "display.wake"),
    ):
        command = display_commands.add_parser(name)
        command.add_argument("television")
        command.add_argument("--timeout", type=float, default=20.0)
        command.set_defaults(
            handler=command_controller_request,
            controller_action=action,
        )

    remote = commands.add_parser("remote")
    remote_commands = remote.add_subparsers(dest="remote_command", required=True)
    remote_status = remote_commands.add_parser("status")
    remote_status.add_argument("television")
    remote_status.add_argument("--timeout", type=float, default=10.0)
    remote_status.set_defaults(
        handler=command_controller_request,
        controller_action="remote.status",
    )
    remote_devices = remote_commands.add_parser("devices")
    remote_devices.add_argument("television")
    remote_devices.add_argument("--timeout", type=float, default=20.0)
    remote_devices.set_defaults(
        handler=command_controller_request,
        controller_action="remote.devices",
    )
    remote_events = remote_commands.add_parser("events")
    remote_events.add_argument("television")
    remote_events.add_argument("--timeout", type=float, default=10.0)
    remote_events.set_defaults(handler=command_remote_events)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("tv", choices=("qn90b", "qn90f"))
    add_transport_options(preflight)
    preflight.set_defaults(handler=command_preflight)

    qn90b = commands.add_parser("qn90b")
    qn90b_commands = qn90b.add_subparsers(dest="qn90b_command", required=True)
    qn90b_root = qn90b_commands.add_parser("root")
    add_root_options(qn90b_root, QN90B_PAYLOAD_DIRECTORY)
    qn90b_root.add_argument("--command")
    qn90b_root.set_defaults(handler=command_qn90b_root)
    qn90b_uep = qn90b_commands.add_parser("uep")
    add_root_options(qn90b_uep, QN90B_PAYLOAD_DIRECTORY)
    qn90b_uep.add_argument("action", choices=("status", "disable"))
    qn90b_uep.set_defaults(handler=command_qn90b_uep)

    qn90f = commands.add_parser("qn90f")
    qn90f_commands = qn90f.add_subparsers(dest="qn90f_command", required=True)
    qn90f_root = qn90f_commands.add_parser("root")
    add_root_options(qn90f_root, QN90F_PAYLOAD_DIRECTORY)
    qn90f_root.add_argument("--command", action="append")
    qn90f_root.add_argument("--callback-host")
    qn90f_root.add_argument("--bind-host")
    qn90f_root.add_argument("--port", type=int, default=0)
    qn90f_root.add_argument("--accept-timeout", type=float, default=30.0)
    qn90f_root.set_defaults(handler=command_qn90f_root)
    qn90f_uep = qn90f_commands.add_parser("uep")
    add_root_options(qn90f_uep, QN90F_PAYLOAD_DIRECTORY)
    qn90f_uep.add_argument("action", choices=("status", "disable"))
    qn90f_uep.set_defaults(handler=command_qn90f_uep)
    qn90f_serve = qn90f_commands.add_parser("serve")
    add_serve_arguments(qn90f_serve)
    qn90f_serve.set_defaults(handler=command_qn90f_serve)

    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    if arguments.sdb is not None:
        os.environ["SDB"] = str(arguments.sdb.expanduser())
    try:
        status = arguments.handler(arguments)
    except (
        CommandError,
        CapabilityError,
        ConfigurationError,
        ControllerError,
        DaemonError,
        Qn90bError,
        RootAgentError,
        SdbError,
        ServiceError,
    ) as error:
        raise SystemExit(str(error)) from error
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    raise SystemExit(status)


if __name__ == "__main__":
    main(sys.argv[1:])
