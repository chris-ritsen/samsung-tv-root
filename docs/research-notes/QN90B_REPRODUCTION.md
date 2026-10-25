# QN90B root reproduction

> **Research note:** This file preserves implementation and reverse-engineering
> details. It is not an end-user setup guide and may contain dated,
> source-checkout-specific procedures. Start with the
> [quick start](../../QUICKSTART.md) for normal use.

## Target

- Samsung `QN55QN90BAFXZA`
- Tizen 6.5 build `T-PTMAKUC-REL-202310071804`
- Linux 5.4.77 armv7l
- SDK foothold `uid=901(sdk) gid=901(sdk)` with the Tizen System SMACK label

An exact build match is not required for the root attempt. Compatibility is
based on the `T-PTMAKUC` firmware family and individually reviewed compatible
builds, Tizen 6.5 (`/etc/tizen-release` observed as both
`Tizen6.5/TV 6.5.0 (arm)` and `Tizen6/TV 6.5.0 (arm)`), Linux 5.4 on ARMv7,
the PontusM `sdp_sparsemem` layout, and read/write access to
`/dev/sdp_pqe_fdet`. An untested compatible build receives one bounded attempt.
The payload discovers and validates its own task and credential objects, and a
missing object or failed structural check aborts the attempt.

The reviewed compatible build `T-PTMDEUC-REL-202602250226` belongs to a
`QE55S95BATXXH` (S95B), a 2022 PontusM sibling of the tested QN90B: its
`/etc/prd_info.ini` records `Model=T-PTMDEUC`, `Version=T-PTMDEUC-1720.7`, and
`Build=TIZEN-TRUNK2022-PontusM-RELEASE_20260225.1`. Its live fingerprint
matches the tested platform (SDK foothold, Linux 5.4.77, ARMv7, Samsung
`dotnet`, `/dev/sdp_pqe_fdet`, and the PontusM command-line layout), and the
FDET route produced an authenticated UID-0 root agent with the .NET Core 3.1
payload build, including clean agent shutdown. Only that exact reviewed build
is accepted outside the tested family; other builds of the line fail closed
until reviewed. It classifies as `compatible-untested`, never as `tested`, and
the fixed UEP address below has not been validated on it.

Three host-side differences matter on that unit:

- The stock payloads target .NET 6 and abort with a `System.Runtime`
  `6.0.0.0` `FileLoadException` on its .NET Core 3.1.3 CLR. Run
  `make qn90b31-payload` for such units. Preflight reads the active runtime
  with `readlink -f /usr/share/dotnet.tizen/netcoreapp` and selects the 3.1
  payload set only when a 3.1.x CLR is positively identified; custom
  `--payload-directory` values are never switched.
- Direct package-name injections of 487 bytes and above were silently
  discarded, while 475-byte injections and staged scripts still ran. Captures
  therefore stage through `sdb push` above a 448-byte direct ceiling.
- Its 3.1 CLR leaves inherited file descriptors open in child processes
  (unlike .NET 6). The background root-agent launch closes the capture
  descriptor (`3>&-`) so the launch capture reaches EOF once the probe exits.

An occasional small injection was also lost outright on this unit and worked
on a direct retry. A command that fails with no TV callback at all is worth
one retry before deeper debugging.

## Chain

1. Using a Samsung `BN59-01199F` full-button IR remote, enter `12345` in App
   Settings, enable Developer Mode, and configure the development computer's
   IPv4 address.
2. Use `SVE-2025-50109` to execute a shell command as `sdk` through the package
   name passed to `0 appinstall tpk`.
3. Build `FdetProbe.dll` locally and upload it as data.
4. Ask Samsung's signed `/usr/bin/dotnet` to load the managed assembly.
5. Open world-writable `/dev/sdp_pqe_fdet` and use its unchecked `mmap2`
   page-frame offset as an arbitrary physical-memory mapping primitive.
6. Give the current thread a unique 15-byte `comm` tag and private credential
   object, scan validated RAM ranges, and locate the matching `task_struct`.
7. Validate PID, tag padding, adjacent `real_cred` and `cred` pointers, RAM
   bounds, credential reference count, and eight consecutive UID/GID values.
8. Replace only those eight identity words with zero. The current managed
   process immediately becomes UID/GID 0.
9. Launch the requested child command while the process is root.

The QN90B implementation modifies its own credential object. The managed
process exits after launching the bounded root command. Root does not persist
across reboot.

## Commands

From a source checkout, install the host dependencies and .NET 6 SDK described
in the [source instructions](../../README.md#run-from-source). These commands
use `uv`; standalone releases already contain the payloads.

```console
export TV_IP=192.0.2.50
export SDB=/absolute/path/to/tizen-studio/tools/sdb
uv sync --locked --all-groups
make qn90b-payload
uv run samsung-tv-root preflight qn90b "$TV_IP"
uv run samsung-tv-root qn90b root "$TV_IP" --command \
  'id; grep -E "^(Uid|Gid|CapEff):" /proc/self/status'
```

The scan is bounded to physical `0x20000000` through `0x69ffffff`, matching the
validated target's usable RAM. Every candidate receives structural validation
before a write.

## UEP

Samsung UEP remains a separate execution boundary after UID 0. The validated
kernel state word is physical `0x208c26c4`. The payload requires the surrounding
state to match and performs a compare-before-write transition from `1` to `0`:

```console
uv run samsung-tv-root qn90b uep "$TV_IP" status
uv run samsung-tv-root qn90b uep "$TV_IP" disable
```

The transition is volatile and is restored by rebooting the TV.
Unlike the root scan, this fixed UEP address is restricted to the exact tested
build.
