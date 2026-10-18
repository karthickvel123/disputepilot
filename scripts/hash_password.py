"""Generate REVIEWER_PASSWORD_HASH and SESSION_SECRET values for your .env (nothing is stored).

Usage:  python scripts/hash_password.py
"""

import getpass
import hashlib
import secrets


def main() -> None:
    pw = getpass.getpass("Reviewer password: ")
    if len(pw) < 10:
        raise SystemExit("Use at least 10 characters.")
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=16384, r=8, p=1)  # same params as web/auth.py
    print(f"REVIEWER_PASSWORD_HASH={salt.hex()}:{key.hex()}")
    print(f"SESSION_SECRET={secrets.token_hex(32)}")


if __name__ == "__main__":
    main()
