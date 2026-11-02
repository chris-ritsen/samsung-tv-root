"""Verify fresh TV-side root evidence before running host-initiated root."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from uuid import UUID


def verify_boot_proof(
    proof: str, *, current_boot_id: str, previous_boot_id: str
) -> dict[str, object]:
    current = str(UUID(current_boot_id.strip()))
    previous = str(UUID(previous_boot_id.strip()))
    if current == previous:
        raise ValueError("the TV has not completed a new boot")
    markers = re.findall(r"(?m)^BOOT_ID=([^\r\n]+)$", proof)
    if len(markers) != 1 or str(UUID(markers[0].strip())) != current:
        raise ValueError("root proof does not identify the current boot")
    if not re.search(r"(?m)^SELFROOT-PROOF uid=0 gid=0\r?$", proof):
        raise ValueError("root proof header does not confirm UID/GID 0")
    for field in ("Uid", "Gid"):
        identities = re.findall(
            rf"(?m)^{field}:[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)[ \t]*\r?$",
            proof,
        )
        if len(identities) != 1 or any(int(value) for value in identities[0]):
            raise ValueError(f"{field} must confirm four zero identities")
    return {
        "verified": True,
        "boot_id": current,
        "previous_boot_id": previous,
        "uid": 0,
        "euid": 0,
        "gid": 0,
        "egid": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", type=Path)
    parser.add_argument("--current-boot-id", required=True)
    parser.add_argument("--previous-boot-id", required=True)
    arguments = parser.parse_args()
    try:
        evidence = verify_boot_proof(
            arguments.proof.read_text(),
            current_boot_id=arguments.current_boot_id,
            previous_boot_id=arguments.previous_boot_id,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"boot proof rejected: {error}\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
