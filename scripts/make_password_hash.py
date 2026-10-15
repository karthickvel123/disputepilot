#!/usr/bin/env python3
"""Prompt for a reviewer password and print the scrypt hash for REVIEWER_PASSWORD_HASH."""

import getpass
import sys

from disputepilot.web.auth import hash_password


def main() -> None:
    """Prompt for reviewer password and output formatted scrypt hash."""
    print("DisputePilot Reviewer Password Hash Generator")
    print("-" * 45)

    try:
        password = getpass.getpass("Enter reviewer password: ")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)

    if not password:
        print("Error: Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    try:
        confirm = getpass.getpass("Confirm reviewer password: ")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)

    if password != confirm:
        print("Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    pwd_hash = hash_password(password)
    print("\nGenerated scrypt password hash:")
    print(pwd_hash)
    print("\nAdd this to your .env file:")
    print(f"REVIEWER_PASSWORD_HASH={pwd_hash}")


if __name__ == "__main__":
    main()
