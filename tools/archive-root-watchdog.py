#!/usr/bin/env python3
"""Re-apply volatile archive-root to a Samsung TV after each boot.

The TV itself keeps no root. This host-side watchdog finds the TV, waits for
SDB, acquires archive-root once per reachable boot, and applies a small,
reversible telemetry-stop set. It never uses a kernel or USB exploit.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("SAMSUNG_TV_ROOT_HOME", Path.home() / ".local/share/samsung-tv-root"))
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "samsung-tv-root"
STATE_FILE = STATE_HOME / "watchdog-state.json"
LOG_FILE = STATE_HOME / "watchdog.log"
LOCK_FILE = STATE_HOME / "watchdog.lock"
RELEASE = HOME / "release" / "samsung-tv-root"
SDB = HOME / "sdb"
POLL_SECONDS = 15
FAILURE_BACKOFF_SECONDS = 20
PORT = 26101
MODEL_PREFIX = "TQ55LS03"

# These are the telemetry / ACR / ad components identified on this TV.
# PISA/canalysis markers survive reboot. The remaining units are masked only
# in /run, so this watchdog re-applies them after every TV boot.
COMMANDS = (
    "mkdir -p /opt/usr/share/systemd/system && touch "
    "/opt/usr/share/systemd/system/pisa-service "
    "/opt/usr/share/systemd/system/canalysis-daemon",
    "systemctl --no-block stop pisa-service.path pisa-service.service "
    "adagent-service.service canalysis-service.service",
    "systemctl mask --runtime contents-recognition-service.service "
    "contents-cognition-service-manager.service "
    "contents-ui-detector-service.service "
    "org.tizen.tv.tagpro-service-tv.service "
    "media-analytics-service.service",
    "systemctl --no-block stop contents-recognition-service.service "
    "contents-cognition-service-manager.service "
    "contents-ui-detector-service.service "
    "org.tizen.tv.tagpro-service-tv.service "
    "media-analytics-service.service",
    "systemctl daemon-reload",
    "true",
)


def log(message: str) -> None:
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} {message}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as stream:
            stream.write(line)
    except OSError:
        pass
    print(line, end="", flush=True)


def load_state() -> dict:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(value: dict) -> None:
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_FILE)


def local_ip(tv_host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((tv_host, PORT))
        return sock.getsockname()[0]


def port_open(host: str) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, PORT)) == 0


def model_name(host: str) -> str:
    try:
        with urllib.request.urlopen(f"http://{host}:8001/api/v2/", timeout=2) as response:
            payload = json.load(response)
        return str(payload.get("device", {}).get("modelName", ""))
    except Exception:
        return ""


def looks_like_tv(host: str) -> bool:
    model = model_name(host)
    return not model or model.startswith(MODEL_PREFIX)


def find_tv(last_host: str | None) -> str | None:
    if last_host and port_open(last_host) and looks_like_tv(last_host):
        return last_host
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        address = probe.getsockname()[0]
        probe.close()
    except OSError:
        return None
    network = ipaddress.ip_network(address + "/24", strict=False)
    candidates: list[str] = []

    def check(host: str) -> str | None:
        return host if port_open(host) and looks_like_tv(host) else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        for result in executor.map(check, (str(host) for host in network.hosts())):
            if result:
                candidates.append(result)
    return candidates[0] if candidates else None


def root_once(host: str) -> bool:
    callback = local_ip(host)
    command = [
        str(RELEASE),
        "-o", "json",
        "--sdb", str(SDB),
        "archive-root", "root",
        "--runtime", "6.0",
        "--callback-host", callback,
        "--bind-host", callback,
        "--accept-timeout", "60",
    ]
    for item in COMMANDS:
        command.extend(("--command", item))
    command.append(host)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        log(f"root attempt failed: {type(error).__name__}: {error}")
        return False
    try:
        evidence = json.loads(result.stdout)
    except ValueError:
        log(f"root attempt returned non-JSON rc={result.returncode}: {result.stderr[-300:]}")
        return False
    authenticated = evidence.get("authenticated") is True
    uid = evidence.get("uid")
    cleaned = evidence.get("staging_cleaned") is True
    unchanged = evidence.get("system_files_unchanged") is True
    log(
        "root result "
        f"rc={result.returncode} authenticated={authenticated} uid={uid} "
        f"staging_cleaned={cleaned} system_files_unchanged={unchanged}"
    )
    if result.returncode != 0 or not authenticated or uid != 0 or not cleaned:
        if result.stderr:
            log(f"root stderr: {result.stderr[-300:]}")
        return False
    return True


def run(once: bool = False) -> int:
    if not RELEASE.is_file() or not SDB.is_file():
        log(f"missing runtime files under {HOME}")
        return 1
    STATE_HOME.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another watchdog instance is already running", flush=True)
        return 0
    os.ftruncate(lock_fd, 0)
    os.write(lock_fd, f"{os.getpid()}\n".encode())
    state = load_state()
    last_host = state.get("host")
    armed = False
    log("watchdog started")
    while True:
        host = find_tv(last_host if isinstance(last_host, str) else None)
        if not host:
            if armed:
                log("TV offline; root will be re-applied when it returns")
            armed = False
            time.sleep(POLL_SECONDS)
            continue
        if host != last_host:
            log(f"TV found at {host}")
            last_host = host
            state["host"] = host
            save_state(state)
        if not armed:
            if root_once(host):
                armed = True
                state["last_root_at"] = datetime.now(timezone.utc).isoformat()
                save_state(state)
                log("telemetry controls applied")
            else:
                time.sleep(FAILURE_BACKOFF_SECONDS)
                continue
        if once:
            return 0
        time.sleep(POLL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one acquisition and exit")
    args = parser.parse_args()
    return run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
