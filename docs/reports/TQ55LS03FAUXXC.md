# TQ55LS03FAUXXC — archive-root report

Status: **first-hand, successful**  
Date: **2026-11-03**  
Root route: **archive-root / SDB package-name injection**  
Kernel exploit: **not used**  
USB exploit: **not used**  
Persistence installed: **no**

## Target

| Item | Value |
| --- | --- |
| Model | `TQ55LS03FAUXXC` (55-inch The Frame, 2025, EU) |
| Firmware | `T-PTMFDEUC-0090-1301.0` |
| Platform | Tizen 9.0 |
| Root runtime | .NET 6.0 (explicit `--runtime 6.0`) |
| Tool | `chris-ritsen/samsung-tv-root` v0.0.12 |

The upstream compatibility table listed Frame 2025 (`T-PTMFAKUC-0090`) only as a
static candidate and did not list this European `T-PTMFDEUC` variant. This run is
the first-hand result for that exact firmware.

## Read-only prerequisites

The archive-root route uses the public SDB package-name injection foothold and
Samsung's signed archive launcher. It does not use a kernel or USB exploit.

| Check | Result |
| --- | --- |
| SDB package-name injection | Works (`uid=901(sdk)`, SMACK `System`) |
| `/usr/bin/dotnet` | Present |
| `dotnet` file capabilities | `cap_setgid,cap_sys_admin=ei` |
| `/usr/sbin/sdbd-tarlauncher` | Present, `cap_setgid,cap_setuid=eip` |
| .NET runtime | `/usr/share/dotnet/shared/Microsoft.NETCore.App/6.0.9` |
| `tar --to-command` | Supported |

## Result

`archive-root probe` returned an authenticated root session:

```text
uid/euid/gid/egid = 0/0/0/0
effective capabilities = 0000003fffffffff
SMACK = User
system_files_unchanged = true
staging_cleaned = true
```

A second run executed only the read-only command `id` as the authenticated root
session and returned `uid=0(owner) gid=0(root)`. No files were changed and no
packages were removed.

Evidence:

- [root-probe.json](../../evidence/TQ55LS03FAUXXC/root-probe.json)
- [root-id.json](../../evidence/TQ55LS03FAUXXC/root-id.json)

The evidence files are sanitized; the TV/controller addresses are redacted.

## Reproduction command shape

Replace the placeholders with the owner's current addresses:

```sh
./samsung-tv-root -o json --sdb /path/to/sdb \
  archive-root probe --runtime 6.0 \
  --callback-host <CONTROLLER_IP> --bind-host <CONTROLLER_IP> \
  --accept-timeout 60 <TV_IP>
```

Read-only root command:

```sh
./samsung-tv-root -o json --sdb /path/to/sdb \
  archive-root root --runtime 6.0 \
  --callback-host <CONTROLLER_IP> --bind-host <CONTROLLER_IP> \
  --accept-timeout 60 --command 'id' <TV_IP>
```

## Auto-root on TV restart

A host-side watchdog is included at `tools/archive-root-watchdog.py`. It finds
the TV, waits for SDB, acquires archive-root once per reachable boot, and applies
the telemetry stop set. It does **not** install a TV-side boot hook and does not
make the TV root persistent; root remains volatile and the watchdog reacquires
it after each restart.

The watchdog also creates the persistent PISA/canalysis markers and re-applies
the `/run` masks for content-recognition, content-cognition/UI, tagpro and
media-analytics after each boot.

The tested telemetry stop set is recorded in
[telemetry-apply.json](../../evidence/TQ55LS03FAUXXC/telemetry-apply.json).
The host unit used on the test machine is:

```ini
[Service]
ExecStart=/usr/bin/python3 /home/deck/.local/share/samsung-tv-root/watchdog.py
Restart=always
RestartSec=15
```

The watchdog requires the release binary and SDB at the paths documented in
`tools/archive-root-watchdog.py`; adjust `SAMSUNG_TV_ROOT_HOME` for another host.

## Limits and rollback

- Root is **volatile**; reboot drops it. No boot persistence was installed.
- The agent retains Samsung's `User` SMACK label. UID 0 is not full control of
  every Samsung security boundary.
- The tool reports `system_files_unchanged` and `staging_cleaned`; it stages
  temporary files under `/home/owner/share/tmp/sdk_tools` and removes them on a
  normal run.
- If a run is interrupted, remove only the temporary staging paths:
  `/home/owner/share/tmp/sdk_tools/archive-root-*` and
  `/home/owner/share/tmp/sdk_tools/on-demand/archive-root-*`.
- No debloat, service masking, package removal, Home/startup change, or CleanFrame
  change was made as part of this root result.
- Reboot the TV to return to a non-root session; the watchdog will reacquire
  archive-root when the TV returns if it is running.
- To restore telemetry services, remove the two PISA/canalysis markers, unmask
  the runtime-masked units, reload systemd and start the units. The watchdog
  includes the same list.
- To stop auto-root, stop the host watchdog service/process and remove its
  user-unit autostart link. The TV itself has no root persistence to remove.

## Disclosure

This report contains no credentials, account identifiers, DUID, MAC address,
serial number, or private network address.
