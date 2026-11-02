"""Check the compiled relay's authentication and traffic using loopback only."""

from __future__ import annotations

import argparse
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def verify(assembly: Path) -> None:
    assembly = assembly.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="tvroot-relay-") as temporary:
        directory = Path(temporary)
        token = "a1" * 16
        token_path = directory / "token"
        token_path.write_text(token, encoding="ascii")
        with socket.socket() as upstream, socket.socket() as reservation:
            upstream.bind(("127.0.0.1", 26101))
            upstream.listen(1)
            upstream.settimeout(0.2)
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
            reservation.close()
            with (directory / "output").open("wb") as output:
                process = subprocess.Popen(
                    [
                        "dotnet", str(assembly), str(port), str(token_path),
                        str(directory / "relay.log"),
                    ],
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        assert process.poll() is None, "relay exited before listening"
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                                break
                        except OSError as error:
                            if time.monotonic() >= deadline:
                                raise TimeoutError("relay did not start within 10 seconds") from error
                            time.sleep(0.05)

                    for supplied in (b"", b"short", b"b2" * 16):
                        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                            client.sendall(supplied)
                            client.shutdown(socket.SHUT_WR)
                            assert client.recv(1) == b"", "relay accepted an invalid token"
                    try:
                        unauthorized, _ = upstream.accept()
                    except socket.timeout:
                        pass
                    else:
                        unauthorized.close()
                        raise AssertionError("unauthorized client reached SDB")

                    upstream.settimeout(2)
                    with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                        client.sendall(token.encode("ascii") + b"OPEN")
                        connection, _ = upstream.accept()
                        with connection:
                            connection.settimeout(2)
                            with connection.makefile("rb") as frames:
                                assert frames.read(4) == b"OPEN", "client frame was not relayed"
                            connection.sendall(b"CNXN")
                            with client.makefile("rb") as frames:
                                assert frames.read(4) == b"CNXN", "SDB frame was not relayed"
                except Exception:
                    output.flush()
                    print((directory / "output").read_text(errors="replace"))
                    raise
                finally:
                    process.terminate()
                    process.wait(timeout=5)
    print("relay verification passed: invalid tokens blocked; authenticated frames relayed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assembly", type=Path)
    verify(parser.parse_args().assembly)


if __name__ == "__main__":
    main()
