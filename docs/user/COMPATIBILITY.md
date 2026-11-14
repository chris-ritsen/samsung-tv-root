# TV compatibility

Root results apply to the **exact model and firmware shown**, not every size or
regional variant in a series. Owner-tested means Chris ran the route on his TV.
Reported means another owner supplied a result; the linked reports vary in
detail. Candidate means firmware evidence, **not** a successful TV test or a
promise that the current release works. All routes below start with the
`SVE-2025-50109` SDB package-name foothold unless noted otherwise. Root access
and volatile UEP disable are separate results.

| Status | Exact TV or firmware family | Firmware | Root route and result | Evidence / limitation |
| --- | --- | --- | --- | --- |
| Owner-tested | `QN55QN90BAFXZA` (QN90B) | `T-PTMAKUC-1602.3` | FDET physical-memory route; archive-launcher route also tested | [QN90B reproduction](../research-notes/QN90B_REPRODUCTION.md) |
| Owner-tested | `QN75QN90FAFXZA` (QN90F) | `T-RSMFAKUC-0090-1203.0` | Mali-G510 `CVE-2025-0072` route; archive-launcher route also tested | [QN90F reproduction](../research-notes/QN90F_REPRODUCTION.md) |
| Reported, public release | `QA55QN90FAUXEG` (QN90F) | `T-RSMFUABC-0090-1301.0` | Mali route; authenticated root, full capability mask and volatile UEP disable | [Independent v0.0.3 validation](../research-notes/QN90F_REPRODUCTION.md#tested-targets); the TV UI misspelled the family `RSMFUBAC` |
| Reported, adapted | `QN55Q60BAFXZC` (Q60B) | `T-NKLBAKUC-1720.7` | Archive-launcher route; later boot-time self-root in a [fork](https://github.com/levkropp/samsung-tv-root-untethered/tree/untethered-boot-agent) | [Owner's UID 0 proof and runtime-detection fix](https://github.com/chris-ritsen/samsung-tv-root/issues/1); not stock release behavior |
| Reported, adapted | `UE50AU9072UXXH` (AU9072) | `T-NKLADEUC-2301.1` | Archive-launcher route; authenticated UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/5); requires a .NET 3.1 runtime-path fallback |
| Reported, adapted | `QE77S90CATXXN` (S90C) | `T-PTMCDEUC-2000.2` | Archive-launcher bootstrap through a separate direct-SDB wrapper | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/3) and [downstream source](https://github.com/invaliddayta/s90c-tools); not an unmodified controller test |
| Reported, adapted | `TQ43Q7F3AUXXC` (Q7F3A) | `T-RSLFDEUC-0090`, build `202608061939` | Archive-launcher route; authenticated UID 0 | [Owner's v0.0.9 report](https://github.com/chris-ritsen/samsung-tv-root/issues/5#issuecomment-6338160290); requires runtime-detection fallback |
| Reported, adapted | `UE43DU7100KXXU` (DU7100) | `T-KSU2EDDEUC-0090-REL-202603190204`, 2130.0 | Archive-launcher route; authenticated UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/6); host-side runtime fallback on an older checkout, not an unmodified release test |
| Reported, downstream | `QN43LS03DAFXZA` (Frame 2024) | `T-PTMDAKUC-0090-2130.0` | Archive-launcher probe returned UID 0 | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/8); vendored v0.0.11 code in `quiet-tizen`, with a first-call timing false negative |
| Reported, downstream | `QA55QEF1AULXL` (QEF1A) | `T-RSLFUABC-0090-REL-202608061940` | SDB plus archive-launcher route; authenticated UID 0 | [Owner's evidence](https://github.com/DemonKingSwarn/samsung-tv-tizen-root/blob/main/evidence/root-evidence.json) and [write-up](https://github.com/DemonKingSwarn/samsung-tv-tizen-root/blob/main/ROOTING-RESEARCH.md); adapted host wrapper, not an unmodified release test |
| Reported, public release | `UA43AU7000KXXD` (AU7000) | `T-KSU2EUABC-REL-202607211852` | Unmodified v0.0.11 archive-launcher route; authenticated UID 0 twice | [Owner's report](https://github.com/chris-ritsen/samsung-tv-root/issues/9); frozen Linux host needed an OpenSSL library-path workaround |
| Reported, downstream | `QN85QN90AAFXZA` (QN90A) | `T-NKM2AKUC-2301.1` | SDB plus archive-launcher-based root, later TV-local reacquisition | [Couchroot device record](https://github.com/splitcipher/couchroot/blob/main/docs/lab/devices/qn90a/README.md) and [owner's Reddit report](https://www.reddit.com/r/Tizen/comments/1x3cog3/experimental_release_vetro_allinone_tv_manager/) |
| Reported, downstream | `QN55S90DAFXZA` (S90D) | `T-PTMDAKUC-0090-2130.0` | SDB plus capability/mount-namespace/archive-launcher route | [Owner's route description](https://www.reddit.com/r/Tizen/comments/1wl4e0n/i_made_a_minimal_plexyoutube_launcher_the_default/) and [Couchroot device record](https://github.com/splitcipher/couchroot/blob/main/docs/lab/devices/s90d/README.md) |
| Reported, downstream | `QE50Q80AATXZT` (Q80A) | `T-NKM2DEUC-2301.1` | Vetro's archive-launcher-derived integration; authenticated root agent | [Vetro compatibility record](https://github.com/andrearicci93/vetro#compatibility); not this CLI/release |
| Reported, downstream | `QE43Q67BAUXXH` (Q67B) | `T-NKLBDEUC-1720.7` | Vetro integration reported UID 0 | [Community diagnostic in Vetro](https://github.com/andrearicci93/vetro#compatibility); cold-boot persistence and device controls unverified |
| Reported | `QN55QN85DBGXZD` (QN85D) | `T-PTMDUABC-0090-2130.0` | Archive-launcher route; UID/GID 0 and successful cleanup | [Owner's report #11](https://github.com/chris-ritsen/samsung-tv-root/issues/11); release version not specified; separate ad-service changes do not qualify other models |
| Reported, adapted | `QE65Q60BAUXXN` (Q60B) | `T-NKLBDEUC-1720.7` | Archive-launcher route; authenticated UID 0 | [Owner's report #12](https://github.com/chris-ritsen/samsung-tv-root/issues/12); later boot-agent installation and staging fix belong to the downstream fork |
| Reported, adapted | `QE55LS03AAUXXN` (Frame 2021) | `T-NKM2DEUC-2310.0`, build `202607211844` | v0.0.12 archive payloads; authenticated UID 0 | [Owner's report #14](https://github.com/chris-ritsen/samsung-tv-root/issues/14); macOS TCP relays and explicit runtime 3.1, not unmodified transport |
| Reported, public release | `QN48S90FAEXZA` (S90F) | `T-RSMFAKUC-0090-REL-202607141953` | v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #15](https://github.com/chris-ritsen/samsung-tv-root/issues/15); automatic runtime 6.0; no Mali or UEP qualification |
| Reported, public release | `QN85QN90AAFXZA` (QN90A) | `T-NKM2AKUC-REL-202607211843` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #18](https://github.com/chris-ritsen/samsung-tv-root/issues/18); newer build than the downstream record above; runtime 3.1; UEP untested |
| Reported, public release | `LS27BG652EUXEN` (Odyssey G6) | `T-PTMLWWC-1720.7`, build `202602250227` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #19](https://github.com/chris-ritsen/samsung-tv-root/issues/19); automatic runtime 3.1 and successful cleanup |
| Reported, public release | `QE43Q60AAUXZT` (Q60A) | `T-NKLADEUC-2301.1`, build `202511120357` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #20](https://github.com/chris-ritsen/samsung-tv-root/issues/20); automatic runtime 3.1 and successful cleanup |
| Reported, adapted | `QN55QEF1AFXZX` (QEF1, MX) | `T-RSLFAKUC-0090-1300.9` | Archive-launcher route; authenticated UID 0 | [Owner's report #23](https://github.com/chris-ritsen/samsung-tv-root/issues/23); v0.0.9 source with a direct-SDB wrapper; stock Windows transport failed |
| Reported, public source | `QE65QN95AATXXU` (QN95A) | `T-NKM2DEUC-2310.0`, build `202607211844` | Unmodified v0.0.12 source and payloads; authenticated UID 0 | [Owner's report #29](https://github.com/chris-ritsen/samsung-tv-root/issues/29); runtime 3.1; later persistence and UEP tools are downstream additions |
| Reported, public release | `UE55AU7100KXXU` (AU7100) | `T-KSU2EDEUC-2310.0` | v0.0.11/v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #30](https://github.com/chris-ritsen/samsung-tv-root/issues/30); runtime 3.1; reported internal build is approximate |
| Reported, adapted | `QA85QN85AAUXZN` (QN85A) | `T-NKM2UABC-2301.1` | v0.0.12 archive payload with diagnostic launch script; UID 0 | [Owner's report #31](https://github.com/chris-ritsen/samsung-tv-root/issues/31); SNAT prevented the stock authenticated callback; root was checked with a separate challenge |
| Reported, public release | `UA85DU7700WXXY` (DU7700) | `2130.0`, `T-KSU2EDUABC-0090-REL-202605141701` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 | [Owner's report #32](https://github.com/chris-ritsen/samsung-tv-root/issues/32); automatic runtime 6.0; QN90F model preflight does not apply |
| Reported, public release | `QE50LS01BAUXXH` (Serif 2022) | `T-PTMDEUC-REL-202602250226` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 in two sessions | [Owner's report #35](https://github.com/chris-ritsen/samsung-tv-root/issues/35); FDET and UEP untested; root acquisition itself stages files despite read-only user commands |
| Reported, public release | `QE55Q60CAUXRU` (Q60C) | `T-NKLCEUC-0080-2032.1` | v0.0.12 archive-launcher route; authenticated UID 0 and command execution | [Owner's report #39](https://github.com/chris-ritsen/samsung-tv-root/issues/39); Windows x86-64, automatic runtime 6.0 and successful cleanup |
| Reported, public release | `QA77S85FAEXXY` (S85F) | `T-PTMFUABC-0090-1301.0` | Unmodified v0.0.12 archive-launcher route; authenticated UID 0 in five same-boot sessions | [Owner's evidence in PR #41](https://github.com/chris-ritsen/samsung-tv-root/pull/41); macOS ARM64; runtime 6.0; fifth session used a wrapper around the release; UEP and reboot reacquisition untested |
| Reported, public release | `UN50DU6900FXZA` (DU6900) | Tizen 9.0.0, Linux 5.4.249; firmware build not given | v0.0.12 Windows archive-launcher route; authenticated UID 0 | [Owner's report #16](https://github.com/chris-ritsen/samsung-tv-root/issues/16); runtime 6.0; a Windows Firewall Block rule stopped the first callback; later exit 255 from the archive launcher is unexplained; boot chain is downstream |
| Reported | `QE65Q64AAUXXN` (Q64A) | `T-NKLADEUC-2310.0`, build `202607211854` | Archive-launcher route supplied the initial root | [Owner's report #17](https://github.com/chris-ritsen/samsung-tv-root/issues/17); release version not given; the persistence, UEP and package-signature changes described there are the owner's own |
| Reported, public source | `GQ50Q60BAUXZG` (Q60B) | `T-NKLBAKUC`, firmware 1720 | Source-built archive-launcher probe; UID/GID 0 and full capability mask | [Owner's report #34](https://github.com/chris-ritsen/samsung-tv-root/issues/34); runtime 3.1; the boot-agent fix described there belongs to the downstream fork |
| Candidate, untested | Other QN90B variants using `T-PTMAKUC-1602.3` | `1602.3` | FDET route has an identical vulnerable handler in the decrypted update | Same firmware code is strong evidence, but no other size/region was root-tested here |
| Candidate, untested | Other QN90F variants using the inspected `T-RSMF*` firmware | `1131.0`, `1296.8`, `1301.0` | SDB and archive-launcher prerequisites are present in inspected images | Mali kernel exploitability and the live runtime/preflight remain unverified; 1301.0 is proven only on the model above |
| Candidate, untested | QN80F / Frame 2025 on `T-PTMFAKUC-0090` | `1131.0`, `1301.0` | SDB plus archive-launcher route is a static candidate | Files and SDB pattern found offline; no live root result or proven Mali route |
| Candidate, untested | Other S90F variants on `T-RSMFAKUC-0090` | `1301.0` | SDB plus archive-launcher route is a static candidate | The exact S90F report above does not qualify other variants or the QN90F Mali chain |
| Candidate, untested | QN80H / Frame 2026 on `T-PTMHAKUC-0100` | `1204.6` | SDB plus archive-launcher route is a static candidate | Tizen 10 image inspected offline; no retail root test |

The Q60B, AU9072, and Q7F3A owners worked around Samsung's nonstandard
`dotnet` apphost locally. This repository added runtime detection in v0.0.10,
but those owners have not confirmed an unmodified later release on their TVs.

## When the foothold is refused

Every route here starts with the `SVE-2025-50109` package-name injection. On
these TVs SDB connects and reports the model, but each injected request returns
`closed` within a fraction of a second and nothing runs:

| Exact TV | Platform | SDB daemon plugin | Report |
| --- | --- | --- | --- |
| `UA49NU7100` (NU7100) | Tizen 4, `T-KTM2LUABC-1360.0` | not given | [#33](https://github.com/chris-ritsen/samsung-tv-root/issues/33) |
| `QE55Q60RATXXC` (Q60R) | Tizen 5.0 | `3.7.1_TV_REL` | [#22](https://github.com/chris-ritsen/samsung-tv-root/issues/22) |
| `UN50M75HAGXZD` (M75H) | Tizen 10.0 | `3.8.12_TV_REL` | [#7](https://github.com/chris-ritsen/samsung-tv-root/issues/7) |

The M75H owner found that its daemon rejects backtick and `$` characters in the
package name. No route in this repository works without the foothold, and
`--runtime` or another model profile does not change that. These are
exact-build results, not a claim about every Tizen 4, 5 or 10 TV.

The CLI reports this case separately from an inconclusive timing result. One
owner saw the same `closed` output from Windows `sdb.exe` on a
[QEF1](https://github.com/chris-ritsen/samsung-tv-root/issues/23) where a direct SDB connection ran the injection, so a refusal
seen only through the Windows client is weaker evidence.

## Other prerequisite failures

- [NKL/Tizen 5.5 #37](https://github.com/chris-ritsen/samsung-tv-root/issues/37)
  and [TU8070 #38](https://github.com/chris-ritsen/samsung-tv-root/issues/38):
  `/usr/bin/dotnet` is missing. The current route cannot substitute
  `dotnet-launcher`; choosing `--runtime` does not supply the required host.
- [TU7092 #40](https://github.com/chris-ritsen/samsung-tv-root/issues/40): the
  capability check failed. The report does not yet distinguish an absent
  executable from missing capabilities on an existing one.
- [Q70T #13](https://github.com/chris-ritsen/samsung-tv-root/issues/13): no `/usr/bin/dotnet` on `T-NKMAKUC-2743.0`, and
  `dotnet-launcher` runs assemblies without capabilities. The owner's root came
  from a separate USB kernel exploit, not this tool.
- [M70D monitor #4](https://github.com/chris-ritsen/samsung-tv-root/issues/4): Developer Mode is on but TCP port 26101 refuses
  connections, so no route can start.
- [U8000 #24](https://github.com/chris-ritsen/samsung-tv-root/issues/24), [U7005F #43](https://github.com/chris-ritsen/samsung-tv-root/issues/43), [CU8000 #10](https://github.com/chris-ritsen/samsung-tv-root/issues/10),
  [NU7100 #47](https://github.com/chris-ritsen/samsung-tv-root/issues/47) and [Freestyle #51](https://github.com/chris-ritsen/samsung-tv-root/issues/51): compatibility questions
  without a root result. PR #42's different U8000 unit does not establish a
  result for the exact TV in #24.
- [NU8000 #25](https://github.com/chris-ritsen/samsung-tv-root/issues/25) and [#26](https://github.com/chris-ritsen/samsung-tv-root/issues/26): offline firmware assessment of
  `T-KTM2AKUC-1355.1`; no live result.

A QN90B on a regional build, `T-PTMUABC-REL-202602250226`, was
[rejected by the model preflight](https://github.com/chris-ritsen/samsung-tv-root/issues/52) in v0.0.12 because of its build prefix
and the spelling of its Tizen release. The preflight now treats regional
`T-PTM` builds as `compatible-untested`; the FDET route has not been run on
that TV. An [S95F owner](https://github.com/chris-ritsen/samsung-tv-root/issues/28) reports archive-root working and UEP blocking
the QN90F SWU key method. An [AU7025 owner](https://github.com/chris-ritsen/samsung-tv-root/issues/50) reports root through the
downstream boot-agent fork without giving the firmware.

Root acquisition does not establish persistence, safe package removal, or UEP
bypass. The boot-agent issues describe downstream software not included in the
public releases.

The [QN90D fork's experimental branch](https://github.com/lzongren/samsung-tv-root/blob/codex/qn90d-hdmi-wake-service/docs/qn90d-hdmi-wake.md)
describes archive-root-assisted installation on `QN50QN90DAFXZA`, firmware
`T-PTMDAKUC-0090-2130.0`, without a separate UID-0 proof. A [Q90T owner](https://github.com/chris-ritsen/samsung-tv-root/issues/2#issuecomment-6297686929)
reported root through a different USB-root adaptation after this project's
archive route failed on that TV. Neither result qualifies this CLI on that TV.

An app installation, matching firmware family, or fork alone is not root proof.
For a new result, record the exact model, firmware/build, route, release or
local changes, and an authenticated UID-0 readback. The preflight's `tested`,
`compatible-untested`, and `incompatible` labels cover its platform checks,
not all reports on this page.
