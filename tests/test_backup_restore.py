"""Unit tests for scripts/backup_restore.py."""

import sqlite3
import tarfile
import tempfile
from pathlib import Path

from scripts.backup_restore import create_backup, restore_backup


def test_backup_and_restore_cycle(tmp_path: Path) -> None:
    data_dir = tmp_path / "source_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = data_dir / "evidence_files"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create source SQLite databases with tables
    disputes_db = data_dir / "disputes.db"
    with sqlite3.connect(str(disputes_db)) as conn:
        conn.execute("CREATE TABLE test_table (id INT, val TEXT)")
        conn.execute("INSERT INTO test_table VALUES (1, 'val_alpha'), (2, 'val_beta')")
        conn.commit()

    users_db = data_dir / "users.db"
    with sqlite3.connect(str(users_db)) as conn:
        conn.execute("CREATE TABLE users (id INT, username TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'test_user')")
        conn.commit()

    # 2. Create sample evidence file
    sample_doc = evidence_dir / "doc1.pdf"
    sample_doc.write_bytes(b"%PDF-1.4 test document content")

    # 3. Perform backup
    backup_dest = tmp_path / "backups"
    archive = create_backup(data_dir=data_dir, dest_dir=backup_dest, merchant_id="test_merchant")

    assert archive.exists()
    assert archive.suffix == ".gz"

    # 4. Restore into fresh directory
    restored_dir = tmp_path / "restored_data"
    success = restore_backup(archive_path=archive, target_data_dir=restored_dir)
    assert success is True

    # 5. Verify restored data
    restored_disputes = restored_dir / "disputes.db"
    assert restored_disputes.exists()
    with sqlite3.connect(str(restored_disputes)) as conn:
        rows = conn.execute("SELECT id, val FROM test_table ORDER BY id").fetchall()
        assert rows == [(1, "val_alpha"), (2, "val_beta")]

    restored_users = restored_dir / "users.db"
    assert restored_users.exists()
    with sqlite3.connect(str(restored_users)) as conn:
        rows = conn.execute("SELECT id, username FROM users").fetchall()
        assert rows == [(1, "test_user")]

    restored_doc = restored_dir / "evidence_files" / "doc1.pdf"
    assert restored_doc.exists()
    assert restored_doc.read_bytes() == b"%PDF-1.4 test document content"
