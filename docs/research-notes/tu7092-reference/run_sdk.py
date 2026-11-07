#!/usr/bin/env python3
"""Exact-target SDK command helper; run with patched tizenpwn on PYTHONPATH."""
import argparse
from pathlib import Path

from tizenpwn.sdb import SdbClient
from tizenpwn.tu7000 import assess_target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tv', required=True)
    parser.add_argument('--sdb', type=Path, required=True)
    parser.add_argument('--command', required=True, help='Literal SDK shell command, not a PC command')
    args = parser.parse_args()
    command = args.command.strip()
    if not command:
        parser.error('command is empty')
    client = SdbClient(args.sdb, args.tv)
    assess_target(args.tv, client=client, experimental_eu=True)
    result = client.capture(command, timeout=45)
    print(result.output, end='')
    if '\n[exit:0]' not in result.output:
        raise SystemExit('SDK command did not report success')


if __name__ == '__main__':
    main()
