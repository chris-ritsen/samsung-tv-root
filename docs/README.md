# Documentation

Start with the [quick start](../QUICKSTART.md) to install the host tool, create a
TV profile, run preflight, and open a root shell.

These guides describe v0.0.11 and the current source tree. `archive-root` requires
v0.0.9 or newer, or a source checkout. For older standalone downloads, start with
their bundled documentation or the [v0.0.8 README](https://github.com/chris-ritsen/samsung-tv-root/blob/v0.0.8/README.md).

## End-user guides

- [Host controller](user/CONTROLLER.md): configuration, lifecycle, service, and
  control commands.
- [Remote input](user/REMOTE_POLICY.md): opt-in observation, suppression, and
  remapping.

## Research notes

These files preserve implementation, exploit reproduction, and reverse-
engineering details. They are not setup guides. Commands and observations may
be historical, incomplete, or specific to a source checkout and tested
firmware.

- [Exploit chain](research-notes/EXPLOIT_CHAIN.md)
- [QN90B reproduction](research-notes/QN90B_REPRODUCTION.md)
- [QN90B automatic boot-root report](research-notes/QN90B_BOOT_ROOT.md)
- [QN90F reproduction](research-notes/QN90F_REPRODUCTION.md)
- [U8000 root observations](research-notes/U8000_REPRODUCTION.md)
- [SWU AES extraction](research-notes/AES_EXTRACTION.md)

The [optional boot agent](../boot-agent/README.md) has separate source-build,
manual-deployment and recovery instructions. It is not installed by the host
controller or included as a ready-to-install manager binary in releases.
