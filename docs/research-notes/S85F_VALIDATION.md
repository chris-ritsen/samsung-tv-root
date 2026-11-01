# S85F public-release validation

An independent owner validated the generic archive-launcher route on the exact
TV and firmware below on 2026-11-01. This is a public-release compatibility
report, not a new exploit route or a claim about every S85F variant. See the
[quick start](../../QUICKSTART.md) for general setup.

## Tested target

| Property | Observed value |
| --- | --- |
| Model | `QA77S85FAEXXY`, Australian 77-inch S85F (2025) |
| Firmware shown by the TV | `T-PTMFUABC-0090-1301.0` |
| TV HTTP API platform/model | `Tizen` / `25_PTM_QD` |
| Kernel | Linux `5.4.261`, `armv7l`; build `#1 SMP PREEMPT Wed Jul 1 16:47:42 UTC 2026` |
| Host | macOS on Apple Silicon |
| Release | Unmodified `samsung-tv-root-0.0.12-macos-arm64.tar.gz` |
| Release SHA-256 | `8ee4587462963f8ad0374f921e41050bd9198a7cb0b15899a5f35a7ad8f50f2c` |
| SDB | Official standalone macOS `4.2.36`, x86-64 binary via Rosetta |
| Route | `archive-root root`, using Developer Mode and SDB |
| Runtime selection | `6.0`, `runtime_source: detected`; no explicit runtime override |

The model was checked through the TV HTTP API and the firmware was transcribed
from the TV's information screen. The runtime value is the controller's
selected payload family; the installed .NET patch version was not established.

## Captured results

Five captured sessions in the same TV boot returned the following fields:

```json
{
  "authenticated": true,
  "uid": 0,
  "euid": 0,
  "gid": 0,
  "egid": 0,
  "cap_eff": "0000003fffffffff",
  "smack": "User",
  "runtime": "6.0",
  "runtime_source": "detected",
  "staging_cleaned": true,
  "system_files_unchanged": true
}
```

The [sanitized evidence](evidence/s85f-v0.0.12.json) retains these fields for
each session, the reported preflight file capabilities, and the first session's
complete `id` and `uname -a` command results. It deliberately omits the host
address and unrelated diagnostics. Device serial numbers, MAC addresses,
UUIDs, tokens, and private network configuration are not included.

The first four sessions invoked the release CLI directly. The fifth used a
local host wrapper that checked the TV identity, started SDB, and invoked the
same unmodified release. No source or payload modifications were needed.

The `id` output starts with `uid=0(owner) gid=0(root)` and reports context
`User`. The numeric UID is the root proof; the `owner` name comes from the
route's temporary passwd view. UID 0 does not imply an unrestricted SMACK label.

`system_files_unchanged` checks only `/etc/passwd` and
`/usr/share/sdbd/public.pem` before and after the session. Together with
`staging_cleaned`, it confirms the controller's specific cleanup checks, not a
comparison of the entire TV filesystem.

## Invocation and host workaround

The TV had Developer Mode enabled with the Mac's LAN address as its development
host. SDB connected on TCP port 26101. The existing host SDB daemon initially
failed to complete the connection handshake; running the official binary as a
foreground server resolved it:

```console
"$SDB" fork-server server
```

That server stayed running in one terminal while the release CLI ran in
another. Here `$SDB` is the absolute path to the standalone SDB executable,
`$ROOT_TOOL` is the executable inside the extracted v0.0.12 release, `$TV_IP`
is the TV's LAN address, and `$HOST_IP` is the Mac's LAN address:

```console
"$SDB" connect "$TV_IP:26101"
"$ROOT_TOOL" --sdb "$SDB" -o json archive-root root "$TV_IP" \
  --callback-host "$HOST_IP" --bind-host "$HOST_IP" \
  --command 'id' --command 'uname -a'
```

The host SDB server was also restarted successfully during this validation.
That is separate from restarting the TV.

## Scope and limits

- Confirmed: authenticated root acquisition, root command execution, automatic
  runtime selection, and the controller's cleanup checks on this exact build.
- Not tested: UEP disable, native payload execution after UEP disable,
  persistence or reacquisition after a TV reboot, an interactive root PTY,
  model-specific display/input controls, or the QN90F Mali route.
- The root result does not establish a fix for the owner's startup delay.
  No firmware flashing or system-service disabling was performed.

This report adds documentation only. It does not change platform preflight
classifications or extend the QN90B/QN90F native-control compatibility claims.
