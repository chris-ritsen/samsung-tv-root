import base64

from samsung_tv_root.sdb import build_shell_injection


def test_shell_injection_round_trip() -> None:
    command = "id; uname -a"
    injection = build_shell_injection(command, gate_token="1234abcd")
    encoded = injection.split("%s${IFS}", 1)[1].split("|base64", 1)[0]
    script = base64.b64decode(encoded).decode()
    assert script == "/bin/mkdir /tmp/s-1234abcd 2>/dev/null&&{ id; uname -a;}"


def test_shell_injection_has_no_literal_space() -> None:
    injection = build_shell_injection("printf ok", gate_token="ab")
    assert " " not in injection
