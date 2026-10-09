# TVRoot Manager — Project Brief & Handoff Spec

**Status:** planning document · **Date:** 2026-10-09 · **Fork:** `levkropp/samsung-tv-root-untethered`
**Upstream:** `chris-ritsen/samsung-tv-root` · **Working issue:** https://github.com/chris-ritsen/samsung-tv-root/issues/1
**Inspiration:** https://github.com/GLinnik21/plx-native (LG webOS native Plex client; this project's "step in that direction" is a native, self-rooting, module-managed Tizen TV)

**P1 checkpoint (2026-10-09):** Agent v3.1 now has a token-gated TCP bridge and
the Python CLI can reach it through a local token-injecting proxy. The agent
builds against the preserved TV frameworks. The DLL and bridge token are
installed with a TV-side backup; live bridge acceptance remains pending the
final reboot with Developer Mode `Host PC IP=127.0.0.1`.

This document is a complete handoff. A fresh agent (no prior session memory) should be able
to execute on it after reading: **this file → issue #1 → the fork's `boot-agent/README.md` →
the fork's source tree.** Everything in §1–§2 is *verified fact from the prior session* —
do not re-derive it; everything in §12 is *known-unknowns* — go verify, don't assume.

---

## 0. Mission

Build a **Magisk/Cydia-style manager for rooted Samsung Tizen TVs**, on top of a proven
untethered boot-root. Two hard requirements from the owner, in priority order:

1. **P1 (build this first): persistent desktop→TV connectivity while Developer Mode
   Host PC IP stays `127.0.0.1`.** The TV must keep `127.0.0.1` as its permanent dev
   state (that is what makes it self-root at every boot), yet the desktop must still be
   able to reach it for management. See §5 — the "sdb bridge" solves this.
2. **P2: the full manager** — module system, on-TV UI, and a cross-platform desktop
   (Win/Mac/Linux, ideally Android too) companion app that walks a non-technical user
   through the entire setup with a guided wizard.

Everything else in this doc hangs off those two.

---

## 1. Current state (as of 2026-10-09, everything below is real and verified)

### 1.1 The TV

| | |
| --- | --- |
| Model | QN55Q60BAFXZC (Samsung Q60B 55"), platform `22_NIKEL_UHD` |
| OS | Tizen 6.5.0 (`Tizen6/TV`), kernel `Linux Samsung 5.4.77 armv7l` |
| Build | `T-NKLBAKUC-REL-202602250226`, software `T-NKLBAKUC-1720.7` |
| LAN | TV at `192.168.68.60`, owner's Mac at `192.168.68.59` (DHCP — assume both may change) |
| Dev mode | ON, survives reboots. Enable via `Apps → Settings gear → 12345`. Host PC IP currently `192.168.68.59` |
| Auto-update | OFF (keep it that way) |

### 1.2 What is deployed on the TV right now

The preinstalled app **`com.samsung.tv.ghservice`** (Gaming Hub service) has been
**squatted** by our boot agent:

- `bin/com.samsung.tv.ghservice.dll` = agent **v3** (sha256 `2ce499f708b0…`, matches the
  Mac build byte-for-byte; the agent displays its own dll's SHA256 on screen as a
  version stamp — verify against this hash)
- original dll + runtimeconfig preserved in-place as `.tvbk` siblings, plus a full
  pre-squat tarball on the Mac (§1.3)
- `tizen-manifest.xml` converted `service-application` → `ui-application`
  (`on-boot="true"`, `type="dotnet-inhouse"`), and the matching
  `/opt/dbspace/.pkgmgr_parser.db` row flipped (`app_component='uiapp'`,
  `app_onboot='true'`, `app_nodisplay='false'`)
- chain artifacts staged at `res/selfroot/` (payload dll, runtimeconfig, `public.pem`,
  `passwd`, signed `archive-root-00b0000000000001.tar.gz` + `.signature`)
- agent v3 behavior: boots at every power-cycle via `app-boot-manager` → runs the
  self-root chain **once** (localhost sdbd → injection → payload → tarlauncher → uid 0) →
  writes evidence to `/home/owner/share/tmp/sdk_tools/selfroot-evidence/` → then, if
  devIP ≠ 127.0.0.1 at boot, **retries every 10s forever** (known wart: intended v4
  change is single-shot, see §6)

**Result: with devIP=`127.0.0.1` at boot, the TV acquires uid 0 by itself, no host
involved. Proven multiple times (e.g. 2026-10-09 11:49 EDT run: `SELFROOT-PROOF uid=0
gid=0`, CapEff full, bind-mounted passwd view visible inside the namespace).**

### 1.3 Owner's Mac artifacts (canonical backups + working tree)

- `~/tv-preserve/1720.7/` — everything: `MANIFEST.md` (hashes, gotchas, timeline),
  `ISSUE-draft-untethered-root.md` (= issue #1 body), `evidence/` (boot-run proof
  pulled + SHA256SUMS), `selfroot-artifacts/` (staging generator `build.py`,
  **pinned RSA keypair** `pinned-private.pem` — the archive signatures are pinned to
  it, do not regenerate), `ghui/` (agent source of record), `bixby-promotion-app-backup.tgz`,
  `dbspace/` (pkgmgr DB snapshots), `dotnet-tree.txt`, `dotnet-share.tgz`,
  `dotnet-tizen.tgz` (the TV's `/usr/share/dotnet.tizen` framework assemblies — needed
  to build the agent; not redistributable), `sdbd` (pulled binary), `ghservice-backup.tgz`
- `~/samsung-tv-root/` — clone of the fork. `origin` = fork (ssh), `upstream` =
  chris-ritsen. Branch `untethered-boot-agent` (pushed):
  - `096f12d` archive-root NKLB compat (the `_check_target` ls-fallback, the payload's
    `[staging on-demand]` 3-arg form, common31 SDK-10 build fix)
  - `23b04ae` `boot-agent/` (agent Program.cs, csproj, staging generator, README)
- Identity: all commits are `levkropp <51499221+levkropp@users.noreply.github.com>`
  (repo-local git config). Keep it that way.
- Tooling present on the Mac: Tizen Studio (`~/tizen-studio` — only `sdb` matters),
  `gh` authed as levkropp, .NET SDK 10 (payloads need the §2 build recipe), ilspycmd,
  Python 3.14.

### 1.4 How to get a root shell on the TV today (maintenance access)

With devIP set to the Mac's IP (as now): `~/samsung-tv-root/.venv/bin/python -m
samsung_tv_root --sdb ~/tizen-studio/tools/sdb archive-root root 192.168.68.60 --command '<sh>'`
(prints JSON incl. uid/euid 0). The helper script pattern used all session:
`python3 /tmp/rj.py '<command>'` (same thing, human-readable). **After any TV reboot,
run `sdb kill-server && sdb start-server` on the Mac before connecting** (§2.9).

---

## 2. Hard-won platform facts (REQUIRED READING — each cost a debug cycle)

**Every item here was empirically established on this exact TV. Do not re-derive.**

1. **Boot trigger.** `app-boot-manager.service` (sysinit) launches apps with
   `on-boot="true"`. The flag lives in **two places** and both were flipped together:
   `package_app_info.app_onboot` in `/opt/dbspace/.pkgmgr_parser.db` (plain SQLite on
   rw vdfs `/opt`) and the manifest attribute. Both `svcapp` and `uiapp` components
   boot this way (proven: the agent was converted svcapp→uiapp and still cold-boots).
   .NET apps boot as IL into the `launchpad-process-pool` zygote (`dotnet-hydra-loader`
   → `dotnet-loader`, private .NET 3.1 stack from `/usr/share/dotnet.tizen`).
   **Installed IL is not signature-checked** — SELP/UEP gate native ELF, not IL.
2. **sdbd auth = source-IP check against the cached devIP, applied to TV-local
   clients too.** Raw TCP from the TV itself to `127.0.0.1:26101` is accepted at the
   socket layer but `CNXN` gets *no reply* unless devIP == `127.0.0.1`. Setting
   Host PC IP to `127.0.0.1` makes the TV its own authorized host (same trick
   TizenBrew documents for its installer). **A PC at another LAN IP cannot pass when
   devIP=127.0.0.1.** ← this is the whole reason §5 exists.
3. **devIP is cached by sdbd at startup.** Flipping it live does nothing until reboot.
   Corollary: every "flip" in any UX flow must be followed by a reboot, and the
   reboot *is* the natural apply-button (dev mode toggling generally wants a reboot
   anyway).
4. **UEP blocks `bash <script-file>`** from disk — `[uep][bash] the file is NOT
   signed!!` — even for root contexts. Feeding the script via stdin
   (`cat script | bash`) passes. All TV-side scripting in the agent/injection uses
   stdin.
5. **SELP is path-based, not content-based.** A byte-identical `setcap`-carrying copy
   of `/usr/bin/dotnet` at another path (`/opt/usr/share/selfroot/dotnet`) refuses to
   exec with `Operation not permitted`. → A "no-sdbd" escalation route (self-staged
   cap'd binary) is **dead**. Assume unsigned native ELF from arbitrary paths is
   generally blocked (untested beyond this one case — §12). The sdb-localhost route is
   *the* untethered path.
6. **SMACK.** Pooled apps run as label `User::Pkg::<appid>`, CapEff empty, CapBnd full,
   `NoNewPrivs: 0`. Kernel policy (`/sys/fs/smackfs/load`) grants `x` on
   `System::Tools` (the dotnet label) to `System`, `User`, `_`, `User::Shell`,
   `System::TEF`, `System::Privileged` — **not** to `User::Pkg::*`; `relabel-self` is
   empty. → a boot app **cannot exec the capped `/usr/bin/dotnet` directly** (EACCES,
   confirmed); the sdbd injection context (label `System`, uid 901) can. App dirs
   `res/` are transmute+RO — **apps cannot write into their own `res/`**; writable:
   `/tmp`, `/home/owner/share/tmp/sdk_tools` (777), and the app's data dirs.
7. **The escalation chain (the entire point).** Injection string is the repo's
   `build_shell_injection` shape: `0 appinstall tpk new2.tpk\`printf${IFS}%s${IFS}<b64>|base64${IFS}-d|bash\`.tpk`
   (**≤510 bytes** — enforced by the CLI; oversize breaks the parser, observed as
   silent `CLSE`). Injected commands run as **uid 901(sdk), label `System`**. From
   there: `/usr/bin/dotnet` (file-capped `cap_setgid,cap_sys_admin+ei`) runs
   `SamsungTvArchiveRoot.dll` → `unshare(CLONE_NEWNS)` + private-tree propagation →
   bind-mounts of a staged `passwd` over `/etc/passwd` and a staged `public.pem` over
   `/usr/share/sdbd/public.pem` → `sdbd-tarlauncher` (file-capped
   `cap_setgid,cap_setuid+eip`) with `--package_name <pkg> -xzf <staged signed
   tar.gz> --to-command=/bin/sh` → **uid 0 shell** whose `launch.sh` streams from the
   archive. Package name must be `archive-root-` + 16 hex (validated by the payload).
8. **SSAP/control channel is always reachable from the LAN regardless of devIP.**
   `GET http://<tv>:8001/api/v2/` returns JSON with `developerMode`, `developerIP`,
   `PowerState`, `model`, `duid` (8002 = https, self-signed). ← manager discovery &
   wizard verification channel. Remote-key WebSocket also lives here (classic
   `samsung.remote.control` channel) — usable by the manager for remote control.
9. **Mac-side sdb quirk:** after a TV reboot the Mac `sdb` server holds stale state;
   `sdb kill-server && sdb start-server` before `connect` (or `devices` shows the TV
   as connected while commands fail with "target not found").
10. **Payload build quirk (Mac, .NET SDK 10):** `make common31-payload` fails
    (`global.json` pinned `6.0.428`, and no restore for the `netcoreapp3.1` TFM).
    Recipe: remove `payloads/common31/global.json`, then
    `dotnet restore ../common/SamsungTvArchiveRoot.csproj -p:TargetFramework=netcoreapp3.1`
    then `dotnet build … --no-restore` into `out/`. (Also fixed on the fork branch.)
11. **App labeling gotchas for deploys:** files copied by the agent into `/tmp` get
    the app's SMACK label with transmutation — the payload (running as `System`) could
    read them fine; keep using `/home/owner/share/tmp/sdk_tools` (777, mixed labels
    work — `cp` over existing files preserves inode labels, verified). The payload's
    explicit `[staging on-demand]` arg form (fork commit `096f12d`) exists so the
    agent can point the payload at these paths.
12. **Don't touch:** ro rootfs (`/dev/root` vdfs ro), `/etc` config, the boot chain,
    firmware. Everything we do lives on rw `/opt` and `/mnt/systemrw`-style storage.
    Recovery = restore ghservice from `.tvbk`/tarball via any root shell.

---

## 3. Goal: Magisk/Cydia concept → TVRoot equivalent

| Magisk / webOS Homebrew Channel | TVRoot (this project) | Status |
| --- | --- | --- |
| Patched ramdisk / boot trigger | `on-boot` uiapp + pkgmgr DB flip (rw storage) | **proven** |
| su daemon (`magiskd`) | boot self-root chain (agent → localhost sdbd → injection → payload → tarlauncher) | **proven** |
| `su` for apps | TV-side root service (RPC/socket, token auth) for modules & manager | P3 |
| ADB access for manager | **sdb bridge** (relay TV:LAN-port → 127.0.0.1:26101, §5) — makes the *existing* desktop CLI work unchanged | **P1 — build first** |
| systemless mounts (`magisk --init`) | payload's private namespace + bind views (`passwd`, `public.pem`) — extend to per-module bind overlays | **proven** for the chain; module overlays P3 |
| `modules/` + `post-fs-data.sh` / `service.sh` | `/opt/usr/share/selfroot/modules/<id>/` + `boot.sh`, run by the rooted agent each boot | P2/P3 |
| Magisk app (module browser) | on-TV NUI manager (grow the existing status window) + desktop/Android companion | P4/P5 |
| repo / Cydia sources | JSON module index in the fork (+ optional third-party source URLs) | P6 |
| Safe mode | flag file / held-key → skip modules (and optionally the root chain) | P3 |
| Zygisk (in-proc hooks) | out of scope (would need signed-ELF or IL-hook tricks — §13) | n/a |

---

## 4. Architecture (target)

```
            ┌───────────────────────────── TV (every boot) ─────────────────────────────┐
            │ app-boot-manager ─ aul ─ agent IL (uiapp, on-boot, uid 5001 in .NET pool)   │
            │     │  self-root chain (localhost sdbd → injection → payload → tarl.)     │
            │     ▼                                                                        │
            │  uid 0 root context ──► module runner ──► modules/<id>/boot.sh              │
            │     │                                              │                          │
            │     └──► sdb bridge: TcpListener 0.0.0.0:<port> ──► splice ──► 127.0.0.1:26101
            │           (token-gated; started by agent after root)                       │
            └────────────────────────────────────────────────────────────────────────────┘
                 ▲  SSAP :8001 (discovery / wizard verification / remote keys)
                 ▲  sdb-over-bridge (full existing CLI: push/pull/shell/injection)
   desktop ──────┘
   manager (P5) ── discovery, wizard, module install/update, logs, backup/restore
```

Components: **agent v4** (boot app: chain + bridge + module runner + UI) · **sdb bridge**
(inside agent) · **on-TV UI** (NUI) · **desktop/Android companion** · **module index +
CI**. The desktop companion is *optional* for daily use — the TV self-roots with no host
at all — it exists for setup, module management, and logs.

---

## 5. P1 — sdb bridge (the first thing to build)

**Problem.** devIP must stay `127.0.0.1` (that's the self-root resting state), but sdbd
only authorizes the source IP == cached devIP, so the desktop is locked out of `26101`.

**Design.** A plain TCP relay, run by the agent on the TV, bound to the LAN:

```
desktop sdb ──► TV:<bridge-port> ──[relay, source=127.0.0.1]──► 127.0.0.1:26101 (sdbd sees an authorized local client)
```

- Relay in C# inside the agent (`TcpListener` + two pump threads; ~50 lines). **No root
  needed to bind** (high port), but the agent only starts it after the boot chain
  succeeds (so it's also a root-status signal).
- **Auth: fixed 32-hex-byte token as the first bytes on each connection** (compare,
  then splice). Token stored at `/opt/usr/share/selfroot/bridge.conf` (persistent rw),
  generated at install time by the manager, which also records it. Optional extra:
  source-IP allowlist entry.
- **Effect: the entire existing desktop toolchain works unmodified.** The repo CLI
  just gets pointed at `<tv-ip>:<bridge-port>` (`sdb connect <ip>:<port>`, or extend
  `SdbClient`/`sdb.py` with an explicit port param — trivial). The archive-root route's
  TV→Mac callback socket (`route_callback_host`) works fine over the LAN; only sdbd's
  *inbound* check was ever the blocker.
- Port pick: `26103` (26101 taken by sdbd; 26102 was used as a MITM port in the prior
  session). Configurable.

**Acceptance (P1):**
1. devIP=127.0.0.1, TV rebooted. Agent boots, self-roots, bridge listens.
2. From the Mac: `sdb connect <tv>:26103` (after token handshake — extend `sdb.py`
   `connect()` to prepend the 32-byte token, or wrap with a tiny local proxy on the
   Mac that injects the token; pick one, document it).
3. Full `archive-root root …` round-trip succeeds through the bridge (uid 0 verified).
4. Bridge refuses connections with a wrong/absent token; logs attempts to evidence dir.
**Do this before anything else — it unblocks all subsequent work *and* it is the
manager's post-install verification channel (§5 of the wizard).**

---

## 6. P2 — agent v4 (rewrite of `boot-agent/`)

Current v3 works but has warts. v4 changes, in order:

1. **Bridge (§5) + start-after-root.**
2. **Single-shot chain at boot** (no retry-forever): try localhost sdbd for a bounded
   window (~3 min covers sdbd coming up late), then park with a clear status
   (`SKIPPED (devIP != 127.0.0.1)` vs `ROOTED` vs `FAILED: <reason>`). Rationale: a
   live flip does nothing (§2.3), so steady-state retry is pointless.
3. **Module runner hook** (P3 runs inside it).
4. **Safe mode:** flag file `/opt/usr/share/selfroot/safe-mode` → skip chain+modules
   (agent still shows UI). Later: also a held-key variant via `TVInputDevice` grab.
   Manager (or `touch` over bridge) toggles the file; agent checks at boot.
5. **Dedicated appid migration** (replaces ghservice squatting): synthesize a fresh
   package (`package_app_info` INSERT + manifest dir + res staging + `on-boot='true'`
   + a `dotnet-inhouse` svcapp/UI pair as needed), then restore ghservice to stock.
   **INSERT is untested** (only UPDATE proven) — that's a §12 recon item; keep squatting
   as fallback until proven.
6. Keep the **on-screen version stamp** (build time + runtime SHA256 of own dll) — it
   solved real "which build am I looking at" confusion.
7. Rebuild against the TV's own framework assemblies (`TV_FRAMEWORK_DIR`, see
   `boot-agent/boot-agent.csproj`; the tgz is in `~/tv-preserve/1720.7/dotnet-tizen.tgz`).

---

## 7. P3 — module system

**Format** (`/opt/usr/share/selfroot/modules/<id>/`, staged by manager over bridge):

```
module.json:
  { "id": "telemetry-acr-off", "name": "Disable ACR/viewing telemetry",
    "version": "1.0.0", "description": "…", "author": "…",
    "scripts": { "install": "./install.sh", "boot": "./boot.sh", "uninstall": "./uninstall.sh" },
    "minAgent": "4" }
boot.sh / install.sh / uninstall.sh   (run via cat-file-into-bash — stdin, UEP-safe, §2.4)
optional payload files…
```

- Enabled/disabled state: per-module `enabled` flag in a central
  `/opt/usr/share/selfroot/modules/state.json` (root-written; UI/manager flips it).
- **Runner:** after chain success at boot, the agent's root context iterates enabled
  modules, runs `boot.sh` with `MODULE_DIR`, `LOG_DIR`, `ROOT_RPC` env, captures
  output to `/opt/usr/share/selfroot/logs/<boot-ts>/<id>.log`. Failure → mark errored,
  continue, surface on TV UI + evidence. Never abort boot.
- **Module API (v1, keep tiny):** helpers documented (paths, env, how to request a
  root command via the agent socket, how to log). No framework, just conventions.

**First modules (the point of all this — telemetry debloat):**
1. `telemetry-acr-off` — enforce Viewing Information Services off + interest-based ads
   off. Needs §12 recon (which vconf/buxton/settings keys; re-verify at each boot).
2. `ad-daemons-off` — neutralize `adagent-service` (pisa), `canalysis-daemon`,
   `slive-provider-daemon`, `context-aware-service`. **These are `Restart=always`
   systemd units on ro `/usr`** — plain `kill` respawns. Robust approaches: iptables
   egress blocks by peer IP (root has full caps) + boot-time kill; or check if
   `systemctl` supports runtime masking to `/run` (tmpfs, writable). Recon §12.
3. `dns-block` — likely better done at the router; keep TV-side variant as optional
   (iptables-based) after recon.
4. `evidence-fetch`, `backup-restore` as manager features rather than modules.

**Safety rules for modules:** no ro writes, no firmware/SELP games, idempotent boot
scripts, everything reversible via uninstall or safe mode, no telemetry of their own.

---

## 8. P4 — on-TV manager UI (grow the agent's NUI window)

The agent already renders: banner, version stamp, progress bar, 11-line log pane.
Extend to:
- Status card: ROOTED / SKIPPED / FAILED + last-boot time, bridge port + token hint.
- **Pairing panel:** show a QR (and plain text) with `tvroot://<tv-ip>:<bridge-port>/<token>`
  so the desktop/Android manager can adopt the TV by scanning (or copy the string).
- Module list (from `modules/state.json`): name, version, enabled, last-boot result;
  toggle via the UI (needs the agent to accept UI→root commands through the same
  local RPC the runner exposes — keep it localhost-only + token).
- Log viewer (tail last boot's logs).
- Keep it a *status/configuration* surface — the browsing/install experience lives in
  the desktop companion (P5); the TV UI stays small and safe.

---

## 9. P5 — desktop/Android companion wizard (UX is the product)

**The guided flow (owner-specified; implement exactly, with verification at each step):**

1. **Discover** — SSDP/mDNS scan + probe `:8001/api/v2/` per candidate; list Samsung
   Tizen TVs with model/duid/devMode/devIP. ("Select your TV.")
2. **Prep** — if devMode off: on-screen instructions + diagrams for
   `Apps → Settings gear → 12345 → Developer Mode ON` (the app cannot press remote
   keys for the user; SSAP remote can *later*, but enabling dev mode must be manual).
3. **First flip** — "On your TV, set Developer Mode **Host PC IP** to **<this
   machine's LAN IP, auto-detected>**, then OK, then reboot." Manager **polls
   `:8001`** (`developerIP`) until it matches, detects the reboot (power state /
   port flap), waits for `26101`, then connects (native sdb client — **no Tizen
   Studio dependency**, see below) and verifies build compatibility
   (build string, dotnet caps, runtimes — the preflight from the repo CLI).
4. **Install** — downloads prebuilt payloads + agent from the fork's CI releases
   (no local .NET SDK needed), generates staging artifacts (fresh or pinned keypair),
   pushes agent dll/runtimeconfig/res staging, flips pkgmgr row + manifest, backs
   up everything it displaced (tarball + hashes, stored both on the Mac and in
   `/opt/usr/share/selfroot/backups/` on the TV), writes `bridge.conf` (bridge token),
   records evidence hashes.
5. **Second flip** — "Now set Host PC IP to **127.0.0.1** and reboot **one final
   time**." Manager waits for the TV to come back, then **connects through the
   bridge** (`<tv>:26103` + token) and verifies the boot-root end-to-end (reads
   `selfroot-evidence/`, checks `uid=0`). ← P1 must exist for this step; it is also
   the manager's permanent operating channel afterwards.
6. **Done screen** — meanwhile the **TV shows the agent's UI**: ROOTED banner, QR/pairing,
   and "further instructions" pointing at the desktop manager for module browsing.
   Post-setup, devIP stays `127.0.0.1` **forever**; the manager never needs another flip
   except for a fresh-TV install.

**Cross-platform implementation — decide at kickoff (present to owner):**

| Option | Stack | Pros | Cons |
| --- | --- | --- | --- |
| A (recommended) | **Tauri 2** (Rust core + system webview UI); Android target | One codebase incl. Android; small binaries; sdb client is ~200 lines of Rust (protocol fully documented, §11/App A); russh if SSH ever needed | Rust learning curve; webview quirks |
| B | Python backend (reuse fork's `samsung_tv_root` as a lib) + local web UI; Termux on Android | Fastest to build — the CLI logic already exists | "Web app" feel; Android = Termux only |
| C | Flutter (desktop + Android) | Native feel everywhere; Dart ssh/sdb pkgs exist | Rewrites all CLI logic in Dart |

Independent of the choice: **implement the sdb client natively in the manager** (kill the
Tizen Studio requirement — it's the single biggest install pain), and **bundle/download
the prebuilt .NET payloads from the fork's releases**.

---

## 10. P6 — repo, index, CI

Fork layout (branch `untethered-boot-agent`, keep master as clean upstream mirror):

```
boot-agent/        agent v3→v4 (IL), staging generator, README        [exists]
manager/           desktop+Android companion (P5)                    [new]
modules/           first-class module sources + index.json            [new]
docs/              protocol notes, this PLAN, gotchas                 [new]
.github/workflows/ extend existing payload CI with manager builds     [extend]
```

- `modules/index.json`: `[{id, name, version, description, dir/url, sha256}]`; manager
  resolves entries to a git ref (raw.githubusercontent) — third-party sources later
  (same file format, user-added source URLs).
- CI: payloads already build on the fork's Actions (Linux/macOS/Windows per upstream
  README); add manager artifact builds (Tauri targets + optional Android APK) and a
  module-packaging check (schema validation, sha256 generation).
- Keep the fork's public tree scrubbed (no LAN IPs, no personal paths) — the privacy
  sweep pattern from the prior session (`git grep -E "Users/|192\.168|…"` before push).

---

## 11. Phasing & milestones (suggested)

| # | Milestone | Depends on | Rough effort |
| --- | --- | --- | --- |
| M0 | Recon checklist §12 (ssh?, INSERT?, daemon-kill persistence, settings keys) | — | ½ day |
| M1 | **sdb bridge + token auth + CLI-through-bridge** (P1 acceptance) | M0 (port/token decision) | 1–2 days |
| M2 | Agent v4: single-shot, bridge, safe-mode, dedicated-appid (if INSERT works) | M1 | 2–3 days |
| M3 | Module runner + format + `telemetry-acr-off` + `ad-daemons-off` | M2 | 2–3 days |
| M4 | On-TV UI v0.1 (status/pairing/module toggles/logs) | M3 | 1–2 days |
| M5 | Desktop companion wizard v0.1 (discovery→install→verify), tech decision §9 | M1 (bridge) | 3–5 days |
| M6 | Module index + CI + docs + first tagged release | M3/M5 | 1–2 days |

Work M1 → M2 → M3 can proceed while M5 is designed in parallel; the bridge unblocks
everything (it is both the tooling channel and the wizard's verification channel).

---

## 12. Open questions — recon checklist (verify before building on)

1. **Is there a usable sshd/dropbear on the TV?** (`which sshd dropbear; ls /usr/sbin`)
   — if yes, the bridge gains a second transport for free (root chain can start it).
2. **Does an unsigned native ELF exec from arbitrary paths** (beyond the dotnet copy
   tested)? Expect no (UEP) — confirms "everything stays IL or Samsung's binaries."
3. **`package_app_info` INSERT** (synthetic appid) — untested; needed for M2's
   de-squatting. Try on the TV, carefully, with the DB backed up first.
4. **Daemon suppression:** is there any writable systemd drop-in path (`/run`,
   `/mnt/systemrw`) that lets us mask `Restart=always` units, or do modules need
   iptables egress blocks + periodic kill? Enumerate what the ad/telemetry daemons
   actually connect to (strings + dlog + `ss`).
5. **ACR/viewing-info settings storage:** which vconf/buxton key or settings DB row
   backs "Viewing Information Services", and does writing it from root persist and
   survive reboot?
6. sdbd's **vconf key name for devIP** (strings suggested a callback exists) — low
   priority; the bridge makes it moot, but knowing it could allow runtime flips.
7. SSAP 8002 TLS cert shape (self-signed pinning for the manager) + the
   `samsung.remote.control` WebSocket auth (TokenAuthSupport was true) for manager remote.
8. Agent crash resilience: does `app-boot-manager` re-launch, or does the UI app need
   to be self-healing (v4 assumption: self-healing only)?
9. Confirm bridge token threat model with owner (LAN-only + 32-hex token OK? add
   source-IP allowlist?).

---

## 13. Non-goals & safety rails

- **No firmware modification, no ro-partition writes, no SELP/UEP bypass games** —
  the entire design rides Samsung's own signed loaders (dotnet, sdbd-tarlauncher) and
  unsigned-but-unchecked IL. Keep it that way (it's also what makes it survivable).
- No Zygisk-style in-process hooking, no anti-detection anything — owner-authorized
  device, no adversary.
- Nothing phones home except explicitly-user-requested GitHub fetches for the module
  index/updates; log everything locally (evidence dirs); scrub personal data from
  anything public.
- OTA updates will reset the squatted app (or the dedicated appid row) — manager
  detects (build fingerprint mismatch), re-runs install, restores backups. Never
  brick: worst case is a dead app + restore path that has been rehearsed.
- Licensing: fork is Unlicense (upstream) — keep new code compatible (Unlicense/MIT),
  don't ship Samsung binaries in-repo (framework dlls stay out of tree; `dotnet.tizen`
  tgz lives only on the owner's Mac).

---

## Appendix A — sdb wire format (verified against captured traffic; the client is ~200 lines)

- Framing: 24-byte header, all fields little-endian:
  `cmd(4, ASCII) · arg0(4) · arg1(4) · data_len(4) · checksum(4) · magic(4)` + payload.
- **checksum = 32-bit byte-sum of payload** (not CRC32; verified).
- **magic = ~cmd** (bitwise NOT of the LE command u32; e.g. CNXN `0x4e584e43` →
  `0xb1a7b1bc`).
- Handshake (from the captured desktop-CLI session):
  - C→T `CNXN` arg0=0x00100000 arg1=0x00040000 payload `"host::\0"` (31 bytes total;
    captured hex: `434e584e000010000000040007000000320200 00bcb1a7b1686f73743a3a00`)
  - T→C `CNXN` payload `"device::QN55Q60BAFXZC::0\0"` + feature banner (k/v pairs,
    incl. `sdbd_version: 2.2.31`, `sdbd_rootperm: disabled`, …)
  - C→T `OPEN` arg0=<local_id e.g. 0x10> payload `"capability:\0"` → T→C `OKAY`
    (arg0=server_id, arg1=local_id) → C→T `OKAY` (echo back) — **do this handshake
    before the service OPEN** (the CLI does; skipping it was implicated in a silent
    CLSE during bring-up)
  - C→T `OPEN` payload `"shell:<command>\0"` (arg0=<local_id e.g. 0x12>) → `OKAY` echo
    → read stream until `CLSE`.
  - Injection OPEN service string: `shell:` + `build_shell_injection`-style string
    (see §2.7); **≤510 bytes total**.
- Reference implementation (C#, TV-side client): fork `boot-agent/Program.cs` — the
  desktop client is the same frames from the other socket end (mirror of `sdb.py`).

## Appendix B — deployed-state dossier (paths that matter on the TV)

```
/opt/usr/apps/com.samsung.tv.ghservice/bin/com.samsung.tv.ghservice.dll     agent v3 (sha256 2ce499f708b0…)
/opt/usr/apps/com.samsung.tv.ghservice/bin/*.tvbk                           pre-squat originals
/opt/usr/apps/com.samsung.tv.ghservice/res/selfroot/                         staged chain artifacts (6 files)
/opt/usr/apps/com.samsung.tv.ghservice/tizen-manifest.xml                   ui-application, on-boot="true"
/opt/dbspace/.pkgmgr_parser.db                                               package_app_info row: uiapp|onboot=true|nodisplay=false
/opt/usr/share/selfroot/                                                      (created; currently only the dead v2 dotnet copy — reusable)
/home/owner/share/tmp/sdk_tools/selfroot-evidence/                            boot-run proof (persistent)
/home/owner/share/tmp/sdk_tools/archive-root-00b0000000000001{,.tar.gz,.signature}  working staging
/tmp/selfroot-app/                                                            agent working dir (tmpfs — wiped at boot)
/usr/share/dotnet.tizen/                                                      TV framework assemblies (agent build inputs; pulled to Mac too)
```

Mac-side: `~/samsung-tv-root` (fork clone, branch `untethered-boot-agent`),
`~/tv-preserve/1720.7/` (canonical backups, hashes, evidence, keypair, issue draft).
Keep both updated as work proceeds; the MANIFEST.md there is the running lab notebook.

## Appendix C — session-proven commands (cheat sheet)

```sh
# discovery / status (works no matter devIP):
curl -m 5 -s http://192.168.68.60:8001/api/v2/          # devMode, developerIP, model…

# sdb connect (Mac), after TV reboot: kill-server/start-server first
~/tizen-studio/tools/sdb connect 192.168.68.60:26101

# root shell as JSON (when devIP = Mac's IP):
~/samsung-tv-root/.venv/bin/python -m samsung_tv_root \
  --sdb ~/tizen-studio/tools/sdb archive-root root 192.168.68.60 --command 'id'

# payload build (Mac, SDK 10): see §2.10 recipe; outputs payloads/common31/out/
# agent build: TV_FRAMEWORK_DIR=…/dotnet.tizen/framework dotnet build boot-agent -c Release
```

*End of brief. First move for the implementing agent: M0 recon (§12, items 1–5), then P1
bridge (§5) to its acceptance criteria.*
