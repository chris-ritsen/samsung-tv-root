import base64
import subprocess
from pathlib import Path

import pytest

from samsung_tv_root.sdb import SdbClient, SdbError, build_shell_injection


def test_shell_injection_round_trip() -> None:
    command = "id; uname -a"
    injection = build_shell_injection(command, gate_token="1234abcd")
    encoded = injection.split("%s${IFS}", 1)[1].split("|base64", 1)[0]
    script = base64.b64decode(encoded).decode()
    assert script == "/bin/mkdir /tmp/s-1234abcd 2>/dev/null&&{ id; uname -a;}"


def test_shell_injection_has_no_literal_space() -> None:
    injection = build_shell_injection("printf ok", gate_token="ab")
    assert " " not in injection


def test_require_device_accepts_ready_serial(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(
        ("sdb", "devices"),
        0,
        "List of devices attached\n192.0.2.50:26101\tdevice\tQN90F\n",
        "",
    )
    monkeypatch.setattr(client, "run", lambda *args, **kwargs: result)

    client.require_device()


def test_require_device_rejects_missing_serial(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(
        ("sdb", "devices"),
        0,
        "List of devices attached\n",
        "",
    )
    monkeypatch.setattr(client, "run", lambda *args, **kwargs: result)

    with pytest.raises(SdbError, match="not listed"):
        client.require_device()


def test_require_shell_injection_accepts_closed_transport(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    injections: list[str] = []

    def inject(command: str, **kwargs) -> subprocess.CompletedProcess[str]:
        injections.append(command)
        return subprocess.CompletedProcess(("sdb",), 1, "", "closed\n")

    def run(arguments, **kwargs) -> subprocess.CompletedProcess[str]:
        remote_path = Path(arguments[3])
        token = remote_path.name.rsplit("-", 1)[1]
        Path(arguments[4]).write_text(token, encoding="ascii")
        return subprocess.CompletedProcess(("sdb",), 0, "pulled\n", "")

    monkeypatch.setattr(client, "inject", inject)
    monkeypatch.setattr(client, "run", run)

    client.require_shell_injection()

    assert len(injections) == 2
    assert injections[0].startswith("/bin/printf ")
    assert injections[1].startswith("/bin/rm -f ")


def test_require_shell_injection_reports_missing_marker(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(("sdb",), 1, "", "closed\n")
    monkeypatch.setattr(client, "inject", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        client,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ("sdb",), 1, "", "remote file does not exist\n"
        ),
    )

    with pytest.raises(SdbError, match="did not create a retrievable marker"):
        client.require_shell_injection()


def test_capture_timeout_reports_active_listener_and_injection_exit(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(("sdb",), 1, "", "closed\n")
    monkeypatch.setattr(client, "inject", lambda *args, **kwargs: result)
    listeners: list[tuple[str, str, int]] = []

    with pytest.raises(SdbError) as failure:
        client.capture(
            "id",
            callback_host="127.0.0.1",
            bind_host="127.0.0.1",
            timeout=0.01,
            on_listening=lambda callback, bind, port: listeners.append(
                (callback, bind, port)
            ),
        )

    message = str(failure.value)
    assert listeners and listeners[0][:2] == ("127.0.0.1", "127.0.0.1")
    assert f"127.0.0.1:{listeners[0][2]}" in message
    assert "listener" in message
    assert "SDB injection exited 1: closed" in message
    assert "inbound firewall" in message


def test_capture_timeout_surfaces_injection_failure(monkeypatch) -> None:
    client = SdbClient(Path("sdb"), "192.0.2.50")
    result = subprocess.CompletedProcess(("sdb",), 2, "", "rejected\n")
    monkeypatch.setattr(client, "inject", lambda *args, **kwargs: result)

    with pytest.raises(SdbError, match="SDB injection failed with exit 2: rejected"):
        client.capture(
            "id",
            callback_host="127.0.0.1",
            bind_host="127.0.0.1",
            timeout=0.01,
        )
