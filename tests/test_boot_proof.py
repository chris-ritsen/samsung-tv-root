import subprocess
import sys
from pathlib import Path

import pytest

from tools.verify_boot_proof import verify_boot_proof


BEFORE = "11111111-1111-4111-8111-111111111111"
AFTER = "2e108aa0-74f6-4e28-96b1-d63527b36780"
PROOF = (
    "SELFROOT-PROOF uid=0 gid=0\n"
    f"BOOT_ID={AFTER}\n"
    "Uid:\t0\t0\t0\t0\n"
    "Gid:\t0\t0\t0\t0\n"
    "CapEff:\t0000003fffffffff\n"
)


def test_current_boot_root_proof_is_accepted() -> None:
    evidence = verify_boot_proof(
        PROOF, current_boot_id=AFTER, previous_boot_id=BEFORE
    )
    assert evidence["verified"] is True
    assert evidence["boot_id"] == AFTER
    assert evidence["uid"] == evidence["euid"] == 0


@pytest.mark.parametrize(
    ("proof", "current", "previous"),
    (
        (PROOF, AFTER, AFTER),
        (PROOF.replace(AFTER, BEFORE), AFTER, BEFORE),
        (PROOF.replace(f"BOOT_ID={AFTER}\n", ""), AFTER, BEFORE),
        (PROOF + f"BOOT_ID={AFTER}\n", AFTER, BEFORE),
        (PROOF.replace("uid=0", "uid=901"), AFTER, BEFORE),
        (PROOF.replace("Uid:\t0\t0\t0\t0", "Uid:\t0\t901\t0\t0"), AFTER, BEFORE),
        (PROOF.replace("Gid:\t0\t0\t0\t0", "Gid:\t0\t0\t901\t0"), AFTER, BEFORE),
        (PROOF.replace("Gid:\t0\t0\t0\t0\n", ""), AFTER, BEFORE),
        (PROOF, "not-a-boot-id", BEFORE),
    ),
)
def test_stale_or_incomplete_proof_is_rejected(proof, current, previous) -> None:
    with pytest.raises(ValueError):
        verify_boot_proof(proof, current_boot_id=current, previous_boot_id=previous)


def test_staging_reuses_key_and_includes_boot_id(tmp_path: Path) -> None:
    import tarfile

    builder = Path(__file__).resolve().parents[1] / "boot-agent/staging/build.py"
    arguments = (sys.executable, str(builder), "--output", str(tmp_path))
    subprocess.run(arguments, check=True, capture_output=True)
    original_key = (tmp_path / "pinned-private.pem").read_bytes()
    original_public = (tmp_path / "public.pem").read_bytes()
    subprocess.run(arguments, check=True, capture_output=True)
    assert (tmp_path / "pinned-private.pem").read_bytes() == original_key
    assert (tmp_path / "public.pem").read_bytes() == original_public
    if sys.platform != "win32":
        assert (tmp_path / "pinned-private.pem").stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "private.pem").stat().st_mode & 0o777 == 0o600
    with tarfile.open(tmp_path / "archive-root-00b0000000000001.tar.gz") as archive:
        script = archive.extractfile("launch.sh").read().decode()
    assert 'BOOT_ID=$(cat /proc/sys/kernel/random/boot_id)' in script
