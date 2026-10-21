# DisputePilot Privacy Policy (Pilot Template)

**Effective Date:** March 2026  
**Applicability:** DisputePilot Single-Merchant Payment Dispute Management Deployment

---

## 1. Introduction & Regulatory Scope

DisputePilot ("the Platform") operates as an automated, human-in-the-loop dispute defense and evidence management system for merchants accepting payments via Razorpay.

This Privacy Policy describes how personal and transactional data is collected, processed, and safeguarded in compliance with:
- The **Digital Personal Data Protection Act, 2023 (DPDP Act)** of India.
- **Reserve Bank of India (RBI)** Master Directions on Payment Aggregators and Payment Gateways.
- **Payment Card Industry Data Security Standard (PCI-DSS v4.0)** requirements.
- Card Network Chargeback Rules (Visa, Mastercard, RuPay, American Express).

---

## 2. Roles: Data Fiduciary vs. Data Processor

- **Merchant (The Enterprise)**: Acts as the **Data Fiduciary** (Controller). The merchant determines the purpose of collecting customer data during order fulfillment and payment acceptance.
- **DisputePilot Deployment**: Acts as the **Data Processor**. The platform processes order, delivery, and dispute records solely on behalf of and under the instruction of the merchant to evaluate and contest payment chargebacks.

---

## 3. Categories of Data Processed

| Category | Specific Data Points | Purpose |
| :--- | :--- | :--- |
| **Transaction Identifiers** | Payment ID, Order ID, Dispute ID, Acquirer Reference Number (ARN) | Dispute case reconciliation with Razorpay |
| **Customer Order Details** | Customer Name, Email, Phone (masked where feasible), Delivery Address | Order fulfillment verification and customer identity matching |
| **Evidence & Delivery Records** | Courier AWB Tracking Numbers, Delivery Timestamps, Recipient Proof of Delivery (POD) | Proof of fulfillment for chargeback representation |
| **Customer Communications** | Support Chat Transcripts, Email Correspondence, Cancellation Notes | Evidence of customer agreement and service utilization |
| **Audit & Authentication Logs** | Operator Usernames, Timestamps, IP Addresses, Cryptographic Action Tokens | Tamper-evident ledger of dispute decisions and role-based access |

### Non-Negotiable PCI-DSS Scope Exclusion
DisputePilot **NEVER** collects, stores, or processes Primary Account Numbers (Full 16-digit PANs), Card Verification Values (CVV/CVC), or Card PINs/OTPs. All document uploads undergo pre-ingestion regex and OCR sanitization to strip unmasked payment card credentials before durable storage.

---

## 4. Legal Grounds for Processing

Data is processed under the following legal bases recognized under Section 4 and Section 7 of the DPDP Act:
1. **Contractual Performance**: Fulfilling purchase and contest representation commitments made between the customer, merchant, and issuing bank.
2. **Legitimate Uses & Legal Compliance**: Complying with statutory fraud monitoring, RBI chargeback representation timelines, and financial transaction auditing rules.

---

## 5. Third-Party Subprocessors & Data Sharing

DisputePilot shares data strictly with verified subprocessors necessary to contest disputes:
1. **Razorpay Software Private Limited**: Inbound webhooks and outbound dispute evidence submissions via official Razorpay APIs (`/v1/disputes`, `/v1/documents`).
2. **Google Cloud / Google AI (Gemini API)**: Used exclusively for document field extraction and rebuttal drafting. Merchant data sent to the enterprise Gemini API is **not** used to train foundation models and is discarded post-inference in accordance with Google Cloud enterprise terms.
3. **Card Networks & Issuing Banks**: When an evidence contest is formally submitted by the merchant, Razorpay transmits the documentation to the customer's card-issuing bank via Visa, Mastercard, or RuPay settlement networks.

---

## 6. Technical & Organizational Security Measures

- **Encryption in Transit**: TLS 1.3 enforced for all web and API traffic (`HSTS: max-age=31536000`).
- **Encryption at Rest**: AES-256 volume encryption for durable disks containing SQLite databases and evidence attachments.
- **Cryptographic Audit Ledger**: Every case modification, document upload, and dispute submission is appended to a Merkle-linked, tamper-evident SHA-256 hash chain (`audit.db`).
- **Access Control**: Session-authenticated role-based access control (Admin, Reviewer, Auditor), account lockout after 5 failed attempts, per-IP rate limiting, and single-use cryptographic `ApprovalToken` requirements for financial state changes.

---

## 7. Data Subject Rights & Retention

Under the DPDP Act, customers whose personal data is processed have rights to:
- Confirm whether their personal data is being processed.
- Request correction of inaccurate order or address details.
- Request erasure of personal data once the statutory chargeback limitation period (typically 120–180 days from transaction date under card network rules) and statutory tax/accounting retention periods have expired.

---

## 8. Grievance Officer & Contact

For inquiries regarding data protection and security practices:
- **Designated Security & Grievance Contact**: `security@merchant.internal`
- **Response Timeline**: Acknowledged within 48 hours; resolved within 30 days.
