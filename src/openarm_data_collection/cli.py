"""Command-line helpers for OpenArm data collection."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence


def run_command(command: Sequence[str], dry_run: bool) -> int:
    """Run or print a command.

    Parameters:
        command: Command and arguments, already split for ``subprocess``.
        dry_run: When true, print without executing.

    Returns:
        Process return code, or zero for dry-run commands.
    """

    printable = " ".join(command)
    print(f"+ {printable}")
    if dry_run:
        return 0
    return subprocess.run(command, check=False).returncode


def setup_can(dry_run: bool = False) -> int:
    """Configure OpenArm 2.0 CAN FD interfaces and set zero positions.

    Parameters:
        dry_run: Print commands without executing them.

    Returns:
        Zero if every command succeeds, otherwise the first failing return code.
    """

    commands = [
        ["openarm-can-cli", "can_configure"],
        ["ip", "link", "show", "can0"],
        ["ip", "link", "show", "can1"],
        ["openarm-can-cli", "-i", "can0", "set_zero", "--arm"],
        ["openarm-can-cli", "-i", "can1", "set_zero", "--arm"],
    ]
    for command in commands:
        code = run_command(command, dry_run=dry_run)
        if code != 0:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the project command-line parser.

    Returns:
        Configured ``argparse.ArgumentParser``.
    """

    parser = argparse.ArgumentParser(description="OpenArm 2.0 data collection utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup = subparsers.add_parser("setup-can", help="Configure CAN FD and set zero position")
    setup.add_argument("--dry-run", action="store_true", help="print commands without running them")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entrypoint.

    Parameters:
        argv: Optional argument list for tests.

    Returns:
        Process exit code.
    """

    args = build_parser().parse_args(argv)
    if args.command == "setup-can":
        return setup_can(dry_run=args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
