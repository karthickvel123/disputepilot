# DisputePilot Data Retention and Deletion Policy

**Effective Date:** March 2026  
**Applicability:** Single-Merchant Pilot and Production Deployments

---

## 1. Overview & Policy Objective

This policy outlines the retention schedules, backup retention cycles, and secure deletion protocols for data processed by the DisputePilot platform. It balances the merchant's operational need to defend against payment disputes with statutory compliance requirements under the **Digital Personal Data Protection Act, 2023 (DPDP Act)**, **RBI Master Directions**, and **Income Tax Act, 1961**.

---

## 2. Data Classification & Retention Schedules

| Data Category | Included Artifacts | Storage Location | Retention Period | Statutory / Operational Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Active Dispute Worklist** | Open dispute metadata, cached order details, unsubmitted rebuttal drafts | SQLite (`cases.db`, `/var/data/disputepilot`) | **Duration of Dispute + 30 Days** | Required for active adjudication, review, and deadline monitoring. |
| **Closed Dispute Records** | Adjudicated chargeback outcomes, submitted rebuttal letters, Razorpay sync events | SQLite (`cases.db`) | **180 Days from Closure** | Matches maximum card network arbitration and pre-compliance filing windows (Visa/Mastercard). |
| **Evidence Attachments** | Invoices, Courier Proofs of Delivery (POD), Customer Chat Exports | File storage (`/var/data/disputepilot/evidence_files/`) | **180 Days from Closure** | Retained to defend against second-stage arbitration appeals or card scheme compliance inquiries. |
| **Financial Ledger Records** | Payment references, dispute amounts, deduction logs, ARN numbers | SQLite (`cases.db`, `/var/data/disputepilot`) | **7 Years** | Mandatory financial and accounting retention under Section 44AA of the Indian Income Tax Act. |
| **Cryptographic Audit Ledger** | SHA-256 Merkle hash chain of all dispute state mutations and approvals | SQLite (`audit.db`, `/var/data/disputepilot`) | **7 Years** | Forensic immutability and non-repudiation record for regulatory audits. |
| **Operator Sessions & Tokens** | Web session cookies, CSRF tokens, login attempt timestamps | SQLite (`users.db`, memory) | **12 Hours (Configurable TTL)** | Ephemeral authentication state; expired sessions pruned hourly. |

---

## 3. Secure Deletion Procedures

### 3.1 Customer Erasure Requests (DPDP Act Right to Erasure)
When a customer exercises their statutory right to erasure:
1. **PII Masking**: Customer personal identifiable information (name, shipping address, unmasked phone, chat logs) is scrubbed from the active dispute record and replaced with pseudonymized identifiers (e.g., `ANONYMIZED_CUSTOMER_001`).
2. **Audit Ledger Integrity**: Under Section 8(7) of the DPDP Act, financial transaction hashes and cryptographic audit entries (`audit.db`) are preserved because their retention is mandated by law for tax and fraud prevention. No raw PII is stored in the audit action metadata.
3. **Evidence Document Destruction**: Unstructured evidence files containing customer PII (e.g., scanned delivery receipts) are securely unlinked and overwritten after the 180-day chargeback appeal window closes.

### 3.2 Merchant Offboarding / Deployment Decommissioning
Upon conclusion or termination of a DisputePilot merchant pilot:
1. **Final Cryptographic Archive**:
   The operator runs the automated backup utility to create a verified, encrypted archive:
   ```bash
   python scripts/backup_restore.py backup --data-dir /var/data/disputepilot --out-dir /secure/merchant_export
   ```
2. **SHA-256 Manifest Verification**:
   The output manifest (`backup_manifest.json`) is cryptographically signed and handed over to the merchant's data security officer.
3. **Storage Volume Sanitization**:
   All database files (`cases.db`, `audit.db`, `reminders.db`, `users.db`) and evidence directories are deleted from the disk:
   ```bash
   # Secure deletion on persistent disk
   rm -rf /var/data/disputepilot/*
   ```
   If hosted on cloud infrastructure (e.g. Render, AWS EBS, GCP Persistent Disk), the volume is securely destroyed or formatted in accordance with NIST SP 800-88 guidelines.

---

## 4. Disaster Recovery & Backup Retention

- **Backup Frequency**: Automated daily atomic SQLite backup snapshots.
- **Snapshot Retention**:
  - Daily snapshots retained for **30 days**.
  - Monthly snapshots retained for **12 months**.
  - Annual compliance archives retained for **7 years**.
- **Backup Integrity**: Every backup file is compressed with `gzip` and accompanied by a SHA-256 digest manifest. Verification restores are executed quarterly via `python scripts/backup_restore.py restore --verify-only`.
