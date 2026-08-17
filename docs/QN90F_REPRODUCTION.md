# QN90F root reproduction

## Tested target

| Property | Value |
| --- | --- |
| Model | `QN75QN90FAFXZA` |
| Firmware | `1203.0` |
| Build | `T-RSMFAKUC-0090-REL-202512092052` |
| OS | Tizen 9.0, Linux 5.4.261, AArch64 |
| Managed runtime | Samsung 32-bit ARM .NET 6.0.9 |
| GPU | Mali-G510 r48p0, API 1.14 |
| Initial identity | `uid=901(sdk) gid=901(sdk)` |

Preflight classifies the exact build as `tested`. Builds in the same firmware,
kernel, runtime, and Mali-driver family can classify as `compatible-untested`.
Missing platform requirements classify the target as `incompatible` before the
kernel payload runs.

## Setup

Samsung Developer Mode exposes SDB to one configured development computer:

Use a Samsung `BN59-01199F` full-button IR remote for the number-key sequence.

1. Open Smart Hub, Apps, and App Settings.
2. Enter `12345` with App Settings focused.
3. Enable Developer Mode and enter the computer's LAN address.
4. Reboot the TV.

Install Tizen Studio on the computer, then connect its `sdb` client:

```console
export TV_IP=192.0.2.50
export SDB=/absolute/path/to/tizen-studio/tools/sdb
"$SDB" connect "$TV_IP:26101"
"$SDB" devices
```

The tested retail firmware closes a normal `sdb shell`. Root acquisition uses
the package-install command path instead.

From a source checkout, build the QN90F and shared managed payloads:

```console
uv sync --all-groups
make qn90f-payload
```

Release archives already contain those payloads.

## Root session

The preflight and interactive root commands are:

```console
uv run samsung-tv-root preflight qn90f "$TV_IP"
uv run samsung-tv-root qn90f root "$TV_IP"
```

A single command can be run instead:

```console
uv run samsung-tv-root qn90f root "$TV_IP" --command \
  'id; uname -a; grep -E "^(Uid|Gid|CapEff):" /proc/self/status'
```

## Exploit chain

1. `SVE-2025-50109` supplies command execution as Samsung's unprivileged `sdk`
   account through the SDB package-name parser.
2. The host uploads managed assemblies as data. Samsung's signed
   `/usr/bin/dotnet` loads them despite UEP blocking direct execution of an
   uploaded native ELF.
3. The QN90F payload triggers the `CVE-2025-0072` Mali USER_IO use-after-free by
   rebinding a command-stream queue and unmapping the stale first mapping.
4. Mali allocator grooming reuses the dangling page as a live GPU L3 page
   table while the stale CPU mapping remains writable.
5. A temporary PTE alias gives the compute path bounded access to selected
   physical pages. Each operation restores the original PTE.
6. Tagged worker threads with private credentials make the current task and
   credential object identifiable in physical RAM without fixed task offsets.
7. One worker's eight Linux identity fields are temporarily changed from 901
   to 0. That worker launches the managed root agent, which inherits root.
8. The worker credentials and temporary GPU PTE are restored and verified
   before the host accepts the root session.
9. The root agent opens an authenticated outbound command channel to the host.

The complete memory-reclaim and credential sequence is described in
[Exploit chain](EXPLOIT_CHAIN.md).

## Validation

The payload records the gates that distinguish a completed exploit from a root
callback produced by damaged state:

- the managed process architecture and Mali r48p0 interface match;
- owned-memory aliases work before physical memory is touched;
- the reclaimed L3 table has the expected PTE structure;
- task, thread, credential pointers, reference count, and identity fields match;
- the launched child reports UID and GID 0;
- the worker's original identity fields are restored and read back;
- the modified GPU PTE is restored and read back.

The host rejects a session missing the completion and restoration records.
Root remains volatile and disappears when the TV reboots.

## Implementation map

| Area | Source |
| --- | --- |
| CLI, staging, callback | `src/samsung_tv_root/qn90f.py` |
| Target fingerprint | `src/samsung_tv_root/compatibility.py` |
| Mali native interface | `payloads/qn90f/MaliNative.cs` |
| EGL compute access | `payloads/qn90f/EglComputeContext.cs` |
| USER_IO reclaim | `payloads/qn90f/MaliPageTableReclaim.cs` |
| Task and credentials | `payloads/qn90f/TaskCredentialProbe.cs` |
| Root-agent launch | `payloads/qn90f/RootAgentLaunch.cs` |
| Root command channel | `payloads/common/SamsungTvRootAgent.cs` |

## Unsigned native execution

Root and UEP are separate. Managed payloads and the root agent work through the
signed .NET runtime without changing UEP. The per-boot UEP state is available
through:

```console
uv run samsung-tv-root qn90f uep "$TV_IP" status
uv run samsung-tv-root qn90f uep "$TV_IP" disable
```

The tested QN90F state word is physical `0x20b58030`. The implementation checks
its surrounding kernel state and the expected one-to-zero transition before
writing it. Reboot restores the original state.
