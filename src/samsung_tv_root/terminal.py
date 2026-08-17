from __future__ import annotations

import os
import socket
import sys
import threading


def relay_socket(connection: socket.socket) -> None:
    if os.name == "nt":
        _relay_windows(connection)
    else:
        _relay_posix(connection)


def _relay_posix(connection: socket.socket) -> None:
    import select
    import termios
    import tty

    input_descriptor = sys.stdin.fileno()
    output_descriptor = sys.stdout.fileno()
    original = termios.tcgetattr(input_descriptor) if os.isatty(input_descriptor) else None
    try:
        if original is not None:
            tty.setraw(input_descriptor)
        while True:
            readable, _, _ = select.select((input_descriptor, connection), (), ())
            if connection in readable:
                payload = connection.recv(65536)
                if not payload:
                    return
                os.write(output_descriptor, payload)
            if input_descriptor in readable:
                payload = os.read(input_descriptor, 65536)
                if not payload:
                    return
                connection.sendall(payload)
    finally:
        if original is not None:
            termios.tcsetattr(input_descriptor, termios.TCSADRAIN, original)


def _relay_windows(connection: socket.socket) -> None:
    import msvcrt

    special_keys = {
        "H": b"\x1b[A",
        "P": b"\x1b[B",
        "K": b"\x1b[D",
        "M": b"\x1b[C",
        "G": b"\x1b[H",
        "O": b"\x1b[F",
        "S": b"\x1b[3~",
    }
    stopped = threading.Event()

    def send_input() -> None:
        try:
            while not stopped.is_set():
                character = msvcrt.getwch()
                if character in ("\x00", "\xe0"):
                    payload = special_keys.get(msvcrt.getwch())
                    if payload is None:
                        continue
                else:
                    payload = character.encode("utf-8", errors="replace")
                connection.sendall(payload)
        except (OSError, UnicodeError):
            stopped.set()

    input_thread = threading.Thread(
        target=send_input,
        name="root-shell-input",
        daemon=True,
    )
    input_thread.start()
    output = getattr(sys.stdout, "buffer", sys.stdout)
    try:
        while not stopped.is_set():
            payload = connection.recv(65536)
            if not payload:
                return
            output.write(payload)
            output.flush()
    finally:
        stopped.set()
