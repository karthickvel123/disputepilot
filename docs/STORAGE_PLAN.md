# DisputePilot Data, Storage & Tenancy Architecture Plan

This document outlines the data storage architecture, durability guarantees, single-tenant isolation boundaries, and database migration paths for **DisputePilot**.

---

## 1. Storage Architecture Overview

DisputePilot uses a combination of relational storage (SQLite during pilot, with a verified migration path to PostgreSQL via Alembic) and durable local filesystem storage for evidence documents.

### Storage Locations (Under `DATA_DIR`, default `/data` in production)

| Component | Storage Path | Durability Mechanism |
| :--- | :--- | :--- |
| **Dispute Webhook Events** | `data/disputes.db` | SQLite with atomic unique constraint on `event_id` |
| **Approval Tokens** | `data/approvals.db` | SQLite with atomic conditional update (`used=1`) |
| **Evidence Metadata Locker** | `data/locker.db` | SQLite with SHA-256 deduplication index |
| **Cryptographic Audit Ledger** | `data/audit.db` | SQLite append-only SHA-256 hash-chained ledger |
| **User & RBAC Store** | `data/users.db` | SQLite with PBKDF2-HMAC-SHA256 password hashes |
| **Merchant Comments Store** | `data/comments.db` | SQLite indexed by `case_id` |
| **Durable Evidence Files** | `data/evidence_files/` | Persistent disk volume (named by `{sha256}_{filename}`) |
| **Processed Drafts & Rebuttals**| `data/drafts/` | Persistent disk volume |

---

## 2. Durable Volume Plan (Render & Kubernetes)

In production, DisputePilot **must never run on ephemeral disks**.

### Render Persistent Disk Configuration
In `render.yaml`:
```yaml
services:
  - type: web
    name: disputepilot
    env: docker
    disk:
      name: disputepilot-data
      mountPath: /data
      sizeGB: 10
    envVars:
      - key: DATA_DIR
        value: /data
```

### Kubernetes PersistentVolumeClaim (PVC)
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: disputepilot-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
```

---

## 3. Automated Online Backup & Disaster Recovery

DisputePilot provides an automated online backup utility in `scripts/backup_restore.py`:
- **Atomic Online Backups:** Uses Python's native `sqlite3.Connection.backup` API. SQLite databases are safely snapshotted without acquiring exclusive file locks or taking down live webhook receivers.
- **Integrity Validation:** Every staged database is verified using `PRAGMA integrity_check` before the backup archive is finalized.
- **Evidence Bundling:** All files in `data/evidence_files/` are bundled into the archive.
- **Tamper-Evident Manifest:** A `manifest.json` recording the SHA-256 digest of every database and evidence file is packaged in the compressed `.tar.gz` archive.

### Recommended Backup Cron Job
Run daily at 02:00 UTC:
```bash
python scripts/backup_restore.py backup --data-dir /data --dest /data/backups --merchant-id pilot_merchant_01
```

### Point-in-Time Restore
To restore or verify an archive:
```bash
python scripts/backup_restore.py verify --archive /data/backups/disputepilot_backup_pilot_merchant_01_1720000000.tar.gz
python scripts/backup_restore.py restore --archive /data/backups/disputepilot_backup_pilot_merchant_01_1720000000.tar.gz --target-dir /data
```

---

## 4. Tenancy Model: Single-Tenant Per Merchant

**Architectural Decision: Single-Tenant Isolation ("One Deployment per Merchant")**

1. **Security & Regulatory Isolation:**
   - Under RBI (Reserve Bank of India) and PCI-DSS data protection principles, payment dispute documents contain sensitive customer and transaction details (invoices, delivery addresses, customer communications).
   - To eliminate cross-tenant data leakage risks, authorization bypasses, or shared database corruption during pilot and early production, DisputePilot enforces **single-tenant isolation**: each merchant runs an independent instance with its own dedicated volume, credentials, and database.

2. **Multi-Merchant Data Provenance:**
   - Even within single-tenant deployments, every domain model, audit row, token, and database table includes a `merchant_id` column (defaulting to the configured merchant identifier).
   - This ensures full audit provenance and enables seamless transition to multi-tenant clusters in future releases.

---

## 5. Migration to Managed PostgreSQL (via Alembic)

DisputePilot includes full Alembic database migration tooling for transitioning from SQLite to PostgreSQL.

### Migration Files
- `alembic.ini`: Database migration configuration reading `DATABASE_URL`.
- `migrations/env.py`: Online and offline migration driver supporting PostgreSQL (`postgresql://`).
- `migrations/versions/0001_initial_schema.py`: Complete baseline schema for PostgreSQL and SQLite.

### Running Migrations against PostgreSQL
1. Set the PostgreSQL connection string in `.env`:
   ```bash
   DATABASE_URL=postgresql://user:password@pg-host:5432/disputepilot
   ```
2. Generate static SQL or execute online migration:
   ```bash
   # Preview static DDL
   uv run alembic upgrade head --sql

   # Apply to live database
   uv run alembic upgrade head
   ```
