# UE55TU7092UXXH: Remote PC/CIFS root and DeviceTracker boot persistence

This is a downstream reproduction record for **one owner-tested TV**, verified
through a cold restart on 7 November 2026. It does not add this TV to the stock
`samsung-tv-root` CLI's supported targets. The initial root route was Remote
PC/CIFS, not a successful run of this project's archive-launcher route.

## Exact target

| Field | Observed value |
| --- | --- |
| Model | `UE55TU7092UXXH` |
| Firmware | `T-KTSU2DEUC-2743.0` |
| Build | `T-KTSU2DEUC-REL-202607022000` |
| Platform | Tizen 5.5, Linux 4.1.10, ARMv7 |
| SDK identity | UID 901, SMACK `System` |
| Application owner | UID 5001 |
| TV Node runtime | 4.4.3 |

A matching model name is insufficient: check the build, runtime and file hashes
on each TV. Other screen sizes, regions and firmware releases remain untested.
Do not update or downgrade firmware as an assumed prerequisite for this report.

## What was achieved

- Initial temporary UID/GID 0 and SMACK `System::Privileged` through the
  privileged Remote PC CIFS helper, using an owner-operated RDP/SMB lab.
- Automatic UID/GID 0 execution at boot through the writable DeviceTracker
  script, using Samsung's signed awk interpreter.
- A detached boot worker that restores its own `System::Privileged` context
  and reconnects an authenticated Node 4 root agent to a locally adapted Vetro.
- Vetro launcher recovery after a cold restart, confirmed with the physical
  Home key. In one measured boot, the marker ran at uptime 0.96 s, Vetro's
  service process started at 41.14 s, the root agent at 48.40 s and the launcher
  at 49.79 s. Allow about a minute before diagnosing an initial Home-key failure.

The earlier marker-only cold boot was tested with the controller disconnected.
The later integrated-agent cold boot verified a changed boot ID and matching
boot marker without a manual root bootstrap; the controller was connected for
the read-only verification. These are separate observations.

This is **boot-persistent root**, rather than an immutable firmware unlock.
Updates, resets or changes to the boot path may remove it. It does not establish
that arbitrary unsigned ELF programs run or that UEP/VDFS are disabled.

## Why the ordinary launcher route was insufficient

This TV lacks `/usr/bin/dotnet`, and its signed Samsung .NET host did not provide
the capabilities required by the archive-root adaptation that was tried.
Node 4 also lacks the modern RSA-generation and timing-safe-comparison APIs
used by the stock Vetro root adapter. Neither an installed Vetro app nor an
`unsupported` status is a proof that no other root route exists.

## 1. Establish the temporary root route

Requirements: Linux controller, Python 3.12+, Docker, OpenSSL, Samsung SDB,
Developer Mode pointing to the controller's LAN address, free controller ports
3389 and 445, and an operator at the TV. Use an isolated trusted LAN. The
temporary Remote PC profile and its credentials are removed after each run.

The companion [reference directory](tu7092-reference/README.md) contains a
source patch for the existing [tizenpwn](https://github.com/rackrot/tizenpwn)
Remote PC/CIFS controller. It is pinned to commit
`d62f8bcc5759a97dc00b630a52a0e788bb957bd1`; it is not a patch for this repository's
CLI. Apply it to a separate clean clone and keep its exact-target checks:

```sh
git clone https://github.com/rackrot/tizenpwn.git
cd tizenpwn
git checkout d62f8bcc5759a97dc00b630a52a0e788bb957bd1
git apply --check /path/to/tu7092-reference/tizenpwn-eu.patch
git apply /path/to/tu7092-reference/tizenpwn-eu.patch
```

Set `TV_IP` to your TV's actual address and `SDB` to your Samsung SDB executable.
The following commands run from that patched tizenpwn checkout:

```sh
PYTHONPATH=src python3 -m tizenpwn --sdb "$SDB" -o json \
  preflight "$TV_IP" --experimental-eu
PYTHONPATH=src python3 -u -m tizenpwn --sdb "$SDB" -o json \
  cifs probe "$TV_IP" --experimental-eu \
  --confirm TU7092-EU-T-KTSU2DEUC-2743.0 \
  --accept-saved-profile --accept-timeout 1200
```

Preflight must confirm the exact target above. `compatible-untested` is the
controller's conservative profile label; it is not itself a UID-0 proof.

The lab supplies fresh temporary RDP/SMB details and certificate fingerprint.
Enter them in Remote PC on the TV, follow its `CONNECTED` gate, click **Shared
Folder once**, then follow its `CLICKED` gate. Leave persistent certificate
trust off. Require an authenticated UID-0 result and successful staging/lab
cleanup. For a root command, use the same gates with `cifs command`:

```sh
PYTHONPATH=src python3 -u -m tizenpwn --sdb "$SDB" -o json \
  cifs command "$TV_IP" --experimental-eu \
  --confirm TU7092-EU-T-KTSU2DEUC-2743.0 --accept-saved-profile \
  --command 'id; cat /proc/self/attr/current' --accept-timeout 1200
```

Do not relabel another model as a TU7092 to bypass preflight. The reviewed
executable hashes on this target were:

| Artifact | SHA-256 |
| --- | --- |
| `mount.smb.sh` | `37aaf2f05bf714332a6bf8f14b543ac9584a1b9a051341674a74fc0dd753c57e` |
| `ps_agent` | `402885bce04ca3a04c2cb322cbe83dd96d05e17457717b4627a85b0fdb004c33` |
| `remotepc_rdp` | `5d5b8277b20cae7ec993be7ff8f556a5f04cdff07109beb025c0e377f4dff9e4` |
| `remotepc_uilauncher` | `b87e23127fe04cfab9e2c43468a99a4c4aa0b852fd5923de17104c3cf9d872da` |

## 2. Back up and validate the boot entry

The normal boot branch of Samsung's `init.wrapper` backgrounds
`/opt/data/DeviceTracker/Dlog_buffer.sh` before starting systemd. On this TV
that script and its parent were writable; the original script was root:root,
mode 777, SMACK `_`, **2,844 bytes** and SHA-256:

```text
7bacb5b029bcc932e1ad450895172ff18270bde1894b14612c108a38cb17003c
```

Obtain a byte-exact copy from **your own TV**, keep it off-device, and verify
its size/hash. Preserve the signature trailer and absence of a final newline.
Do not distribute this Samsung script, a decrypted image or signing material.

For example, after the successful preflight/SDB connection, choose a private
directory outside all Git checkouts and pull the original:

```sh
umask 077
PRIVATE_DIR="$HOME/tu7092-private"
mkdir -p -m 700 "$PRIVATE_DIR"
"$SDB" pull /opt/data/DeviceTracker/Dlog_buffer.sh "$PRIVATE_DIR/Dlog_buffer.sh.original"
wc -c "$PRIVATE_DIR/Dlog_buffer.sh.original"
sha256sum "$PRIVATE_DIR/Dlog_buffer.sh.original"
```

The reference generator requires that exact original. It builds files locally;
it never connects to a TV:

```sh
python3 /path/to/tu7092-reference/build_awk_canary.py \
  --original /private/path/Dlog_buffer.sh.original \
  --out /private/path/tu7092-marker
```

Read the generated `report.json`, `install.sh`, `rollback.sh` and `boot` before
using them. The generated output contains the vendor original and must remain
private. The installer verifies UID 0, the exact build, live original hash,
original ownership/mode, absence of an earlier installation and the stop file.
It saves the original, stages and checks new files, then atomically replaces
the one writable DeviceTracker script. It does not write a raw partition or
modify `/etc/profile`, the kernel, global environment or read-only rootfs.

Stage `install.sh` with SDB in an owner-writable directory. Read back its hash
and compare with the local generated report. Through the authenticated root
command channel, run its **contents** with signed Bash, for example:

```sh
"$SDB" push /private/path/tu7092-marker/install.sh /home/owner/share/tmp/sdk_tools/tu7092-marker-install.sh
```

After verifying that staged file, use this TV-side command through the root
channel:

```sh
/bin/bash -c "$(cat /home/owner/share/tmp/sdk_tools/tu7092-marker-install.sh)"
```

Pass that command literally as a root-channel command; do not let the PC shell
expand the command substitution. Direct `bash /path/to/script` and Node script
files were rejected by userspace UEP on the tested TV.

## 3. Verify marker-only persistence before adding an agent

The installed carrier starts with `#!/usr/bin/awk -f`. Its `BEGIN` block attempts
the optional marker command, then invokes the complete original DeviceTracker
body from base64 through signed Bash. Failure of the optional command does not
skip the vendor body. This awk execution path was tested; it is not a claim of
a universal native-code signing bypass.

Remove mains power, leave the controller disconnected, then restart. Reconnect
SDB and compare `/proc/sys/kernel/random/boot_id` with
`/opt/tizenpwn-awk-canary/last-boot.txt`. Require a new matching boot ID,
UID/GID 0 and the capability mask. The tested marker ran with SMACK `_`;
do not claim `System::Privileged` from that marker alone.

## 4. Add the supervised Vetro agent

First prepare the exact-build Vetro external-agent port described in its
`rooting/ports/tu7092/README.md`, build it and sign for your own TV. Keep
Developer Mode Host PC IP at the controller address for this route. The stock
guide's loopback-IP step belongs to the stock TV-local archive route.

The companion `persistent/` sources generate the **same boot carrier** used
in the reported setup, with input paths made portable:

```sh
python3 /path/to/tu7092-reference/persistent/build.py \
  --marker-dir /private/path/tu7092-marker --out /private/path/tu7092-agent
python3 /path/to/tu7092-reference/persistent/prepare_install.py \
  --bundle /private/path/tu7092-agent
```

This is a second-stage update: its guarded installer requires the matching
marker-only carrier already installed. Follow the generated `deployment.json`
staging location, verify both staged files' hashes, and execute the generated
`install-sdk.sh` contents through the existing SDB SDK command foothold.
It requires UID 901 and refuses an unexpected live carrier. An ordinary
`sdb shell` may not expose a Unix shell on this firmware; use the controller's
SDK command mechanism rather than treating `sdb shell <command>` as universal. The reference helper runs the same exact-target preflight first. The reported
bundle's generated stage is shown below; use the value from **your**
`deployment.json` if it differs. From the patched tizenpwn checkout:

```sh
PYTHONPATH=src python3 /path/to/tu7092-reference/run_sdk.py \
  --tv "$TV_IP" --sdb "$SDB" \
  --command 'mkdir -p -m 700 /home/owner/share/tmp/sdk_tools/vetro-boot-update-70fc8c934427'
```

Push `Dlog_buffer.sh`, `rollback-sdk.sh` and `install-sdk.sh` from your generated
agent directory into that TV directory with SDB. Read back their SHA-256 values
through `run_sdk.py` and compare with the PC files before installation. Then:

```sh
PYTHONPATH=src python3 /path/to/tu7092-reference/run_sdk.py \
  --tv "$TV_IP" --sdb "$SDB" \
  --command '/bin/bash -c "$(cat /home/owner/share/tmp/sdk_tools/vetro-boot-update-70fc8c934427/install-sdk.sh)"'
```

The single quotes keep command substitution on the TV. The helper opens a
temporary callback listener for the SDK command, not a persistent root service.

At boot, the carrier unpacks verified, root-owned assets under
`/opt/vetro-tu7092-root`, creates volatile state under `/run/vetro-tu7092-root`,
and detaches a worker. The worker changes **only its own** SMACK context to
`System::Privileged`, checks full effective capabilities, and waits for Vetro's
owner-private configuration. It uses the existing `SAMSUNG-TV-ROOT/1` HMAC
protocol over loopback; private tokens are generated per Vetro service start.
The signed Node process handles protocol traffic and signed Bash executes
bounded commands over private FIFOs. No Node `child_process` is used on the TV.
The worker detects Vetro service/configuration changes and reconnects.

Cold boot again and require all of: new matching boot ID; UID/GID 0 marker;
worker `agent-running` with `System::Privileged`; authenticated Vetro UID/GID 0;
active launcher; physical Home-key confirmation. A working marker alone is
insufficient to validate the complete root-agent chain.

## Recovery

`/opt/data/DeviceTracker/tizenpwn.stop` suppresses the optional boot work; the
wrapper still attempts the vendor body. The full worker also checks this file
and `/opt/vetro-tu7092-root/disabled` while running. A stop file does not restore
the original script or uninstall Vetro.

The marker generator includes root `rollback.sh`, which restores only the known
original/current-carrier hashes and original ownership, mode and SMACK. The
full-agent generator includes `rollback-sdk.sh`, which restores its previous
marker-only carrier and leaves the stop file set. Root rollback can then restore
the vendor original. Run shell-script contents through the appropriate signed
interpreter command path. Do not execute either installer as a rollback.

An SDK byte-restore route was tested while SDB remained available. SDK cannot
restore root ownership; that needs root afterward. No independent recovery
was demonstrated if normal userspace and SDB both fail. Keep the original
and recovery instructions off-device before editing the boot entry.

## Reproduction boundaries and provenance

No firmware image, Samsung script body, serial number, MAC/DUID, LAN address,
certificate, key, root token or raw diagnostic log is included. Shared hashes
identify public-build artifacts, not device credentials. The companion scripts
are source references, with separate host tests; generating them is not a TV test.

The SDB foothold and authenticated agent protocol build on this project's
research. The initial CIFS lab and exact-target checks use tizenpwn; the awk
carrier, Node 4 bridge, boot supervisor and launcher adaptations are downstream
work. The documentation and portability changes were AI-assisted and checked
against the recorded device results. A second physical TV has not been tested.
