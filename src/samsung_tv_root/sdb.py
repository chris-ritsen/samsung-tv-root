from __future__ import annotations

import base64
import os
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


SDB_PORT = 26101
DEFAULT_TIMEOUT = 10.0
DEFAULT_CAPTURE_TIMEOUT = 30.0


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
        candidates.extend(
            Path(root) / "tizen-studio" / "tools" / executable
            for root in (
                os.environ.get("SystemDrive", "C:"),
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


class SdbClient:
    def __init__(
        self,
        executable: Path,
        tv_host: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.executable = executable
        self.tv_host = tv_host
        self.timeout = timeout

    @property
    def serial(self) -> str:
        return f"{self.tv_host}:{SDB_PORT}"

    def connect(self) -> None:
        result = self.run(("connect", self.serial), check=False)
        if result.returncode != 0:
            raise SdbError(command_failure("sdb connect", result))

    def disconnect(self) -> None:
        self.run(("disconnect", self.serial), check=False)

    def push(self, local_path: Path, remote_path: Path) -> None:
        result = self.run(
            ("-s", self.serial, "push", str(local_path), str(remote_path)),
            check=False,
            timeout=max(self.timeout, 15.0),
        )
        if result.returncode != 0:
            raise SdbError(command_failure(f"sdb push {local_path.name}", result))

    def pull(self, remote_path: Path, local_path: Path) -> None:
        result = self.run(
            ("-s", self.serial, "pull", str(remote_path), str(local_path)),
            check=False,
            timeout=max(self.timeout, 30.0),
        )
        if result.returncode != 0:
            raise SdbError(command_failure(f"sdb pull {remote_path}", result))

    def inject(
        self,
        command: str,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        injection = build_shell_injection(command)
        return self.run(
            ("-s", self.serial, "shell", f"0 appinstall tpk {injection}"),
            check=False,
            timeout=timeout or self.timeout,
        )

    def capture(
        self,
        command: str,
        *,
        callback_host: str | None = None,
        bind_host: str | None = None,
        port: int = 0,
        timeout: float = DEFAULT_CAPTURE_TIMEOUT,
    ) -> CaptureResult:
        callback = callback_host or route_callback_host(self.tv_host)
        bind = bind_host or callback
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((bind, port))
            listener.listen(1)
            listener.settimeout(timeout)
            callback_port = int(listener.getsockname()[1])
            wrapped = (
                f"exec 3<>/dev/tcp/{callback}/{callback_port};"
                f"{{ {command}; }} >&3 2>&3;"
                "printf '\\n[exit:%s]\\n' \"$?\" >&3;exec 3>&-"
            )
            state: dict[str, object] = {}

            def launch() -> None:
                try:
                    state["result"] = self.inject(wrapped, timeout=timeout)
                except BaseException as error:
                    state["error"] = error

            worker = threading.Thread(target=launch, name="sdb-injection", daemon=True)
            worker.start()
            try:
                connection, _ = listener.accept()
            except TimeoutError as error:
                failure = state.get("error")
                if isinstance(failure, BaseException):
                    raise SdbError(str(failure)) from failure
                raise SdbError(
                    f"TV callback did not connect within {timeout:g}s"
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
