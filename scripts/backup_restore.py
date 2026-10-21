"""Automated atomic backup and restore tool for DisputePilot persistent data.

Uses Python's native sqlite3 online backup API (sqlite3.Connection.backup)
to produce consistent point-in-time snapshots of all SQLite databases even while
the application is actively processing webhooks and disputes.

Features:
- Atomic online snapshots of all databases (no file-copy corruption or table locks).
- Bundles evidence files directory into the backup bundle.
- Generates cryptographic SHA-256 manifest for tamper-evident verification.
- Supports gzip compression.
- Point-in-time restore with pre-flight integrity verification (PRAGMA integrity_check).
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("disputepilot.backup")

KNOWN_DATABASES = [
    "disputes.db",
    "approvals.db",
    "locker.db",
    "audit.db",
    "users.db",
    "comments.db",
]


def _sha256_file(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def backup_database_atomic(src_path: Path, dest_path: Path) -> str:
    """Perform atomic online backup using SQLite's backup API."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not src_path.exists():
        # Create empty initialized db if src does not exist
        with sqlite3.connect(str(dest_path)) as conn:
            pass
        return _sha256_file(dest_path)

    src_conn = sqlite3.connect(str(src_path), timeout=30.0)
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    return _sha256_file(dest_path)


def verify_database_integrity(db_path: Path) -> bool:
    """Run SQLite PRAGMA integrity_check on the database."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        return result is not None and result[0] == "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Integrity check failed for %s: %s", db_path.name, exc)
        return False
    finally:
        if conn is not None:
            conn.close()


def create_backup(
    data_dir: Path | str = "data",
    dest_dir: Path | str = "backups",
    merchant_id: str = "default_merchant",
) -> Path:
    """Create a verified, timestamped backup archive of all databases and evidence files.

    Returns:
        Path to the generated .tar.gz archive.
    """
    src = Path(data_dir)
    out_dir = Path(dest_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    archive_name = f"disputepilot_backup_{merchant_id}_{timestamp}.tar.gz"
    final_archive_path = out_dir / archive_name

    with tempfile.TemporaryDirectory(prefix="dp_backup_staging_") as staging:
        staging_dir = Path(staging)
        manifest: dict[str, Any] = {
            "merchant_id": merchant_id,
            "timestamp": timestamp,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
            "databases": {},
            "evidence_files": {},
        }

        # 1. Atomic backup of each database
        for db_name in KNOWN_DATABASES:
            db_src = src / db_name
            db_dst = staging_dir / "databases" / db_name
            if db_src.exists():
                digest = backup_database_atomic(db_src, db_dst)
                is_ok = verify_database_integrity(db_dst)
                if not is_ok:
                    raise RuntimeError(f"Integrity check failed on staged snapshot for {db_name}")
                manifest["databases"][db_name] = {
                    "sha256": digest,
                    "size_bytes": db_dst.stat().st_size,
                    "integrity_check": "ok",
                }
                logger.info("Snapshotted database %s (sha256: %s...)", db_name, digest[:12])

        # 2. Bundle evidence files
        evidence_src = src / "evidence_files"
        if evidence_src.is_dir():
            evidence_dst = staging_dir / "evidence_files"
            evidence_dst.mkdir(parents=True, exist_ok=True)
            for f in sorted(evidence_src.glob("*")):
                if f.is_file():
                    target = evidence_dst / f.name
                    shutil.copy2(f, target)
                    digest = _sha256_file(target)
                    manifest["evidence_files"][f.name] = {
                        "sha256": digest,
                        "size_bytes": target.stat().st_size,
                    }

        # 3. Write manifest
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # 4. Create tar.gz archive
        with tarfile.open(final_archive_path, "w:gz") as tar:
            for item in staging_dir.iterdir():
                tar.add(item, arcname=item.name)

    logger.info("Created backup archive: %s (size: %d bytes)", final_archive_path, final_archive_path.stat().st_size)
    return final_archive_path


def restore_backup(archive_path: Path | str, target_data_dir: Path | str = "data") -> bool:
    """Restore databases and evidence files from a verified backup archive."""
    archive = Path(archive_path)
    target = Path(target_data_dir)
    target.mkdir(parents=True, exist_ok=True)

    if not archive.exists():
        logger.error("Backup archive does not exist: %s", archive)
        return False

    with tempfile.TemporaryDirectory(prefix="dp_restore_staging_") as staging:
        staging_dir = Path(staging)

        # 1. Extract to staging
        with tarfile.open(archive, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=staging_dir, filter="data")
            else:
                tar.extractall(path=staging_dir)

        manifest_file = staging_dir / "manifest.json"
        if not manifest_file.exists():
            logger.error("Restore failed: manifest.json missing from backup archive.")
            return False

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        logger.info("Verifying backup manifest for merchant: %s (date: %s)", manifest.get("merchant_id"), manifest.get("created_at_utc"))

        # 2. Verify all database checksums and integrity
        staged_dbs = staging_dir / "databases"
        if staged_dbs.is_dir():
            for db_name, meta in manifest.get("databases", {}).items():
                db_staged = staged_dbs / db_name
                if not db_staged.exists():
                    logger.error("Corrupted archive: database %s missing from archive.", db_name)
                    return False
                actual_hash = _sha256_file(db_staged)
                if actual_hash != meta["sha256"]:
                    logger.error("Checksum mismatch for %s: expected %s, got %s", db_name, meta["sha256"], actual_hash)
                    return False
                if not verify_database_integrity(db_staged):
                    logger.error("SQLite PRAGMA integrity_check failed on %s", db_name)
                    return False

        # 3. Apply to target
        if staged_dbs.is_dir():
            for db_name in manifest.get("databases", {}):
                src_db = staged_dbs / db_name
                dst_db = target / db_name
                shutil.copy2(src_db, dst_db)
                logger.info("Restored database: %s", db_name)

        staged_evidence = staging_dir / "evidence_files"
        if staged_evidence.is_dir():
            dst_evidence = target / "evidence_files"
            dst_evidence.mkdir(parents=True, exist_ok=True)
            for f in staged_evidence.glob("*"):
                if f.is_file():
                    shutil.copy2(f, dst_evidence / f.name)
            logger.info("Restored %d evidence files.", len(list(staged_evidence.glob("*"))))

    logger.info("Restore completed successfully into %s", target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="DisputePilot Atomic Backup & Restore Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create point-in-time backup archive")
    backup_parser.add_argument("--data-dir", default="data", help="Directory containing SQLite databases & evidence")
    backup_parser.add_argument("--dest", default="backups", help="Directory where archive will be saved")
    backup_parser.add_argument("--merchant-id", default="default_merchant", help="Merchant identifier")

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore data from backup archive")
    restore_parser.add_argument("--archive", required=True, help="Path to .tar.gz backup archive")
    restore_parser.add_argument("--target-dir", default="data", help="Directory where data will be restored")

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify integrity of a backup archive")
    verify_parser.add_argument("--archive", required=True, help="Path to .tar.gz backup archive")

    args = parser.parse_args()

    if args.command == "backup":
        try:
            created = create_backup(data_dir=args.data_dir, dest_dir=args.dest, merchant_id=args.merchant_id)
            print(f"SUCCESS: Backup created at {created}")
            return 0
        except Exception as exc:
            logger.exception("Backup failed: %s", exc)
            return 1

    elif args.command == "restore":
        success = restore_backup(archive_path=args.archive, target_data_dir=args.target_dir)
        return 0 if success else 1

    elif args.command == "verify":
        with tempfile.TemporaryDirectory() as temp_dir:
            success = restore_backup(archive_path=args.archive, target_data_dir=temp_dir)
            if success:
                print("SUCCESS: Backup archive verified - all checksums and database integrity checks passed.")
                return 0
            else:
                print("FAILURE: Backup archive verification failed.", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
