"""SQLite evidence locker: merchant-supplied evidence files for a dispute.

Razorpay holds the dispute, payment, order and refund, but not the merchant's own fulfilment
evidence (courier proof, invoice, chat logs ...). Reviewers add that here. Each file is:
  * stored locally (metadata + optional redacted text excerpt, never the raw card data),
  * uploaded to Razorpay's Documents API (purpose=dispute_evidence) to obtain a ``doc_...`` id,
  * referenced by that id in the contest payload.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

# Evidence categories accepted by PATCH /v1/disputes/:id/contest (besides structured `others`).
EVIDENCE_CATEGORIES: tuple[str, ...] = (
    "shipping_proof",
    "billing_proof",
    "cancellation_proof",
    "customer_communication",
    "proof_of_service",
    "explanation_letter",
    "refund_confirmation",
    "access_activity_log",
    "refund_cancellation_policy",
    "term_and_conditions",
)

# Razorpay Documents API: JPEG, PNG and PDF only.
ALLOWED_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class LockerDocument:
    id: int
    dispute_id: str
    category: str
    file_name: str
    mime: str
    size: int
    sha256: str
    razorpay_doc_id: str | None
    excerpt: str
    uploaded_by: str
    created_at: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS locker_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dispute_id TEXT NOT NULL,
    category TEXT NOT NULL,
    file_name TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    razorpay_doc_id TEXT,
    excerpt TEXT NOT NULL DEFAULT '',
    uploaded_by TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_locker_dispute ON locker_documents (dispute_id);
CREATE INDEX IF NOT EXISTS idx_locker_sha ON locker_documents (sha256);
"""


class EvidenceLocker:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row(r: sqlite3.Row) -> LockerDocument:
        return LockerDocument(**dict(r))


    def add(
        self,
        dispute_id: str,
        category: str,
        file_name: str,
        mime: str,
        size: int,
        sha256: str,
        uploaded_by: str,
        razorpay_doc_id: str | None = None,
        excerpt: str = "",
        now: int | None = None,
    ) -> LockerDocument:
        if category not in EVIDENCE_CATEGORIES:
            raise ValueError(f"Unknown evidence category '{category}'.")
        ts = int(time.time()) if now is None else int(now)
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO locker_documents (dispute_id, category, file_name, mime, size, sha256, "
                "razorpay_doc_id, excerpt, uploaded_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (dispute_id, category, file_name, mime, size, sha256, razorpay_doc_id, excerpt, uploaded_by, ts),
            )
            row = c.execute("SELECT * FROM locker_documents WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row(row)

    def list_for_dispute(self, dispute_id: str) -> list[LockerDocument]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM locker_documents WHERE dispute_id = ? ORDER BY id", (dispute_id,)
            ).fetchall()
        return [self._row(r) for r in rows]

    def find_uploaded_by_hash(self, sha256: str) -> LockerDocument | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM locker_documents WHERE sha256 = ? AND razorpay_doc_id IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (sha256,),
            ).fetchone()
        return self._row(row) if row else None

    def evidence_ids(self, dispute_id: str) -> dict[str, list[str]]:
        """Category -> Razorpay document ids for every locker file already uploaded."""
        out: dict[str, list[str]] = {}
        for d in self.list_for_dispute(dispute_id):
            if d.razorpay_doc_id:
                out.setdefault(d.category, []).append(d.razorpay_doc_id)
        return out
