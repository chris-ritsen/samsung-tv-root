# U8000 root observations

Observed on 2026-10-31 through 2026-11-01; these results are separate from the
QN90B and Q60B work.

| Property | Observed value |
| --- | --- |
| Exact model | `UN50U8000FFXZA` |
| Internal build | `T-X22UDFAKUC-0090-REL-202607141244` |
| Platform | `Tizen9/TV 9.0.0 (arm)` |
| Kernel / architecture | Linux `5.4.261`, `armv7l` |
| Active managed runtime | .NET `6.0.9` |
| Initial SDK identity | UID/GID `901`, SMACK `System` |
| Root identity | UID/EUID/GID/EGID `0`, SMACK `User` |

The TV's displayed numeric software version has not been recorded. Tizen 9
does not make this the QN90F kernel target: this model is 32-bit ARM and has a
different firmware family. The verified route is the model-independent
`archive-root` command.

## Verified temporary root

SDB package-name command execution passed the bounded timing probe. The system
`dotnet` has effective SETGID/SYS_ADMIN capabilities, `sdbd-tarlauncher` has
effective SETUID/SETGID capabilities, and tar supports `--to-command`.
Samsung's dotnet rejects `--list-runtimes`; resolving the active runtime
symlink identifies `6.0.9`.

Authenticated root sessions confirmed all four identity values as zero. A CLI
test created, read and removed a UID/GID-0 file with mode `0600` under `/run`.
An EFL notification overlay displayed `ROOT VERIFIED - UID 0` for 20 seconds;
the owner confirmed seeing it. Both checked system files remained unchanged,
and temporary staging and processes were cleaned up.

## Boot installation

The stock `com.samsung.tv.ghservice` application was backed up before changes.
All 14 stock file hashes matched the on-TV backup, and an online SQLite
package-database backup passed its integrity check. Verified recovery copies
and metadata were also saved on the controller.

The manager and relay were built against the TV's framework for .NET 6.
Installation verified 14 deployed hashes and preserved the original manager
binary, runtime configuration and manifest ownership/modes/SMACK labels.
Only `app_onboot`, `app_nodisplay` and `app_component` changed in the package
row. The manifest was converted to a UI application with startup enabled.
The owner confirmed that the installed TVRoot manager is visible.

Only root and the headless bridge module were installed. The stock Gaming Hub
service entry point is repurposed; a dedicated application ID is still future
work. No privacy/debloat or update-disabling modules were installed.

The first full reboot with Host PC IP `127.0.0.1` launched the manager and
reached `ROOT CHAIN RUNNING`, then timed out without fresh proof. Recovery
logs showed SDK execution followed by `.NET: The specified file does not
exist.` The payload existed, but its staging directory/file labels blocked
the runtime's view. Shared staging inodes corrected the payload-load check
and the complete host-triggered startup preflight.

Manager v5.13 subsequently passed a full reboot. A new kernel boot ID and
matching proof with real/effective/saved/filesystem UID and GID all zero were
retrieved through the authenticated headless bridge as SDK UID 901, before
any new host-initiated root. The prior host-triggered proof had been removed
before this test. `tools/verify_boot_proof.py` accepted the fresh evidence.

After that proof was saved, a new root session confirmed UID/GID 0, the same
boot ID and an active `tvroot-bridge.service`. The manager was terminated;
authenticated SDK access through the headless bridge remained available.
All three checked global system-file hashes remained unchanged. Repeated
power cycles, standby/wake, HDMI gaming and actual rollback remain untested.

## Subsequent live verification

On 2026-11-01, the authenticated bridge was reachable on port `26103` with
the manager closed. The current kernel boot ID still matched the verified
boot-root proof. A live read of the running `tvroot-bridge.service` process
confirmed all four UID and GID fields were zero and effective capabilities
were `0000003fffffffff`; this check did not initiate another root chain.

A subsequent authenticated root session displayed the requested custom text
`hello bubby!` for 30 seconds using the existing .NET 6 EFL overlay tool.
The tool reported `overlay_ready duration_s=30` and
`overlay_done reason=timer`. Temporary overlay and root-session files were
removed, and the checked global system-file hashes remained unchanged.
This confirms continued management access on the verified boot; repeated
untethered boots still need separate testing.

## Recovery limits

Direct SDB recovery requires setting Developer Mode Host PC IP back to the
controller's LAN address and fully rebooting. A stock restore script is
prepared with the on-TV backup; actual rollback remains untested.

This TV's SDB pull path restrictions rejected the recovery export even from
the SDK tools directory. The controller fetched it through the SDK callback
and checked its SHA-256 instead. The TV's tar advertises extended attributes
but reports that xattr support is unavailable, so the host tar export alone
does not establish label-preserving recovery. The on-TV `cp -a` backup and
explicit ownership/mode/SMACK records are retained.

Preserve the shared label on the existing SDB `on-demand` directory. Changing
it to `_` caused SDB uploads to fail at close, and the next archive launcher
was rejected. Recreating it with the inherited `User::App::Shared` label
restored the host-root route. This was corrected before activation.

The v5.13 build keeps app-traversed evidence directories shared,
shows outer/payload logs and SDB output in the manager, and provides an
authenticated SDK relay on port `26104` while the manager is open. This relay
does not establish root and is separate from the root-started headless bridge
on port `26103`. Only the fresh identity proof establishes boot-root success.

Pre-create the four fixed-stage payload/config/key/passwd files and launcher
log with SDK-writable modes and `User::App::Shared` labels. SDK copies then
overwrite those inodes without creating `System`-labeled assemblies. Changing
only the parent directory is insufficient for already-created files.

The SmartView HTTP API's `developerIP` field continued reporting the former
desktop IP while direct desktop SDB was rejected and localhost bridge access
worked after reboot. Use the effective connection behavior and kernel boot ID
for this validation; that HTTP field alone did not reliably reflect the change.
