#!/usr/bin/gawk -f
# tvroot AT-HUB persistence hook (module at-hub-persistence).
#
# Installed over the vendor /opt/etc/parseinfo.sh. The stock bytes are
# preserved verbatim at /opt/usr/share/selfroot/backups/parseinfo.sh.stock
# (805 bytes, sha256 c6369e7dec69408e176daa252d436acf6f8e265f560504d8bd831c8023c71d61)
# and shipped inside this module as parseinfo.sh.stock.
#
# AT-HUB.service (vendor unit, /usr/lib/systemd/system/starter.target.wants/)
# executes this path at every boot as root (no User= setting). The stock
# behavior (write __REPO__MODEL__ to /proc/target_version) is preserved
# below; the tvroot boot runner then starts the bridge and runs modules.
#
# UEP notes (live-verified 2026-11-06 on T-NKLBAKUC-1720.7 / Tizen 6.5):
#   - kernel UEP excludes "#!" scripts from its target types, so systemd
#     can exec this file directly (a #!/bin/sh test script execs fine);
#   - /bin/bash and /bin/sh refuse unsigned script FILES via their
#     libkUEPUser.so hook (the stock file carries a ##UEP signature
#     trailer for exactly that reason; an unsigned #!/bin/sh replacement
#     exits 1 with no body executed);
#   - /usr/bin/gawk is signed and not linked against libkUEPUser.so, so
#     it loads this file as plain data;
#   - system() runs /bin/sh -c commands without script-file arguments.
# AT-HUB.service passes a trailing "&" argument (systemd passes the vendor
# ExecStart "&" through as argv); gawk would treat it as an input data file,
# so exit in BEGIN prevents any data file from ever being opened.
BEGIN {
    # vendor write, ported 1:1 from the stock parseinfo.sh pipeline:
    #   Repoinfo=$(cat /etc/prd_info.ini | grep "Build=" | cut -d "=" -f2 | cut -d";" -f1)
    #   REPO=${Repoinfo%*;*} ; same for Model -> echo "__${REPO}__${MODEL}" > /proc/target_version
    repo = ""; model = ""
    while ((getline line < "/etc/prd_info.ini") > 0) {
        if (line ~ /^Build=/) {
            s = line
            sub(/^Build=/, "", s)
            sub(/;.*/, "", s)
            repo = s
        } else if (line ~ /^Model=/) {
            s = line
            sub(/^Model=/, "", s)
            sub(/;.*/, "", s)
            model = s
        }
    }
    close("/etc/prd_info.ini")
    printf "__%s__%s\n", repo, model > "/proc/target_version"
    close("/proc/target_version")
    # tvroot boot runner (bridge + modules), UEP-safe stdin form
    system("cat /opt/usr/share/selfroot/modules/at-hub-persistence/runner.sh | bash >/dev/null 2>&1")
    exit 0
}
