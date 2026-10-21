# DisputePilot Customer Data Flow Architecture

**Effective Date:** March 2026  
**Audience:** Security Architects, Compliance Officers, and Technical Auditors  
**Applicability:** Single-Merchant Pilot & Production Deployments

---

## 1. End-to-End Data Flow Overview

This document specifies the exact flow of customer and transaction data across DisputePilot's processing lifecycle, detailing what data enters the platform, how it is transformed and stored internally, and precisely what data is shared with third parties (**Razorpay** and **Google Gemini**).

```mermaid
flowchart TD
    subgraph External_Inbound[External Inbound Sources]
        RZP_WH[Razorpay Webhooks\n(HMAC-SHA256 Signed)]
        MERCH_ORD[Merchant Order DB / ERP]
        MERCH_EVID[Merchant Evidence Uploads\n(Invoices, PODs, Chats)]
    end

    subgraph DisputePilot_Core[DisputePilot Platform Boundary]
        API_GW[FastAPI Gateway / Ingestion Engine]
        PAN_SCAN[Pre-Ingestion PII & PCI Scanner\n(Strips PANs, CVVs)]
        SQLITE_DB[(Persistent Storage\nAES-256 Volume\ncases.db, audit.db)]
        FACT_SET[FactSet Extractor & Normalizer]
        VERIFIER[Deterministic Rebuttal Verifier\n(Strips Hallucinations & Injections)]
        AUDIT_CHAIN[SHA-256 Merkle Audit Ledger]
    end

    subgraph External_AI[Google Cloud / AI Studio]
        GEMINI[Google Gemini API\n(Enterprise Zero-Retention Endpoint)]
    end

    subgraph External_Outbound[External Financial Outbound]
        RZP_DOCS[Razorpay Documents API\nPOST /v1/documents]
        RZP_CONTEST[Razorpay Disputes API\nPATCH /v1/disputes/:id/contest]
        RZP_ACCEPT[Razorpay Concede API\nPOST /v1/disputes/:id/accept]
        BANK_SCHEME[Acquiring & Issuing Banks\n(Visa, Mastercard, RuPay)]
    end

    RZP_WH -->|Dispute metadata| API_GW
    MERCH_ORD -->|Order & customer details| API_GW
    MERCH_EVID -->|Raw PDFs, images, text| PAN_SCAN
    PAN_SCAN -->|Sanitized documents| API_GW
    API_GW --> SQLITE_DB
    API_GW --> FACT_SET

    FACT_SET -->|Passive text prompt\n(No PANs, no CVVs)| GEMINI
    GEMINI -->|Candidate JSON extraction & draft| VERIFIER
    FACT_SET -->|Ground truth fact tokens| VERIFIER

    VERIFIER -->|Clean, verified draft| SQLITE_DB
    SQLITE_DB -->|Cryptographic token required| AUDIT_CHAIN

    AUDIT_CHAIN -->|Human-authorized evidence| RZP_DOCS
    AUDIT_CHAIN -->|Human-authorized contest summary| RZP_CONTEST
    AUDIT_CHAIN -->|Human-authorized concession| RZP_ACCEPT

    RZP_DOCS --> BANK_SCHEME
    RZP_CONTEST --> BANK_SCHEME
    RZP_ACCEPT --> BANK_SCHEME
```

---

## 2. Detailed Data Ingestion Matrix

| Data Flow Stage | Data Elements | Source | Destination | Encryption |
| :--- | :--- | :--- | :--- | :--- |
| **Inbound Webhook** | Dispute ID, Payment ID, Disputed Amount (paise), Reason Code, Reason Description, Respond By epoch | Razorpay Webhook Gateway | DisputePilot `/webhook/razorpay` | TLS 1.3, HMAC-SHA256 signature verification |
| **Order Ingestion** | Order ID, Customer Name, Email, Masked Phone, Shipping Address, Item Descriptors, Courier AWB | Merchant Storefront / ERP API | DisputePilot Core | TLS 1.3 |
| **Evidence Upload** | Scanned Invoices, Courier Proof of Delivery (POD) slips, Customer Chat Transcripts | Merchant Operator Upload | Durable Storage `/var/data/disputepilot/evidence_files/` | TLS 1.3 in transit, AES-256 volume encryption |

---

## 3. Data Shared with Google Gemini

DisputePilot integrates with Google Gemini to perform bounded entity extraction and generate structured rebuttal drafts.

### 3.1 What IS Sent to Gemini
1. **Dispute Reason Context**: The textual reason code and description provided by the cardholder (e.g. `"Item not received - package never arrived"`).
2. **Passive Evidence Excerpts**: Text extracted from merchant invoices and courier tracking summaries, wrapped in untrusted boundary tokens (`<UNTRUSTED_DATA_BOUNDARY_...>`):
   - Merchant Order ID
   - Customer Name
   - Carrier Tracking Number and Delivery Date
   - Line Item descriptions and totals
3. **Structured Schema Constraints**: Strict JSON schemas defining allowable output fields.

### 3.2 What is NEVER Sent to Gemini
- **Payment Card Data**: No 16-digit card numbers (PANs), CVVs, expiration dates, or OTPs.
- **Merchant Financial Credentials**: Razorpay Key Secrets, Webhook Secrets, or internal Session Secrets.
- **Database Identity Records**: Operator passwords, password hashes, or internal database primary keys.

### 3.3 Gemini Security & Privacy Guarantees
- Calls are made via enterprise Gemini API endpoints.
- Under Google Cloud Terms of Service, prompt and generated data is **never used to train or fine-tune Google AI foundation models**.
- All responses from Gemini pass through DisputePilot's **Deterministic Verifier** (`verify_rebuttal`), which cross-references every sentence against the verified `FactSet`. Any entity, date, amount, or assertional claim not verbatim in the verified facts is automatically stripped.

---

## 4. Data Shared with Razorpay

When a merchant operator reviews, approves, and authorizes contest submission:

| Endpoint | Method | Transmitted Data Elements | Authentication / Authorization |
| :--- | :--- | :--- | :--- |
| `/v1/documents` | `POST` | Binary PDF / JPG / PNG evidence document, purpose tag (`dispute_evidence`) | Basic Auth (`RAZORPAY_KEY_ID:RAZORPAY_KEY_SECRET`), single-use `ApprovalToken` |
| `/v1/disputes/:id/contest` | `PATCH` | Formatted summary narrative (maximum 1,000 characters), list of uploaded Razorpay document IDs (`doc_...`), action (`draft` or `submit`) | Basic Auth, single-use `ApprovalToken` bound to SHA-256 payload digest |
| `/v1/disputes/:id/accept` | `POST` | Dispute ID and acceptance confirmation | Basic Auth, single-use `ApprovalToken` with manual typed amount verification |

---

## 5. Architectural Controls Preventing Data Leakage

1. **Read-Only Evidence Agent Registry**: The Evidence Agent that audits documents only has access to strictly read-only tools (`get_dispute`, `get_order`, `get_refund`, `list_documents`, `get_extracted_doc`). No tool exists in the agent module that can write data, call external APIs, or modify databases.
2. **Cryptographic Separation of LLM from Execution**: LLMs never issue approval tokens or trigger HTTP mutations. State mutations require an out-of-band human reviewer session.
3. **Audit Log Sanitization**: Audit logging in `src/disputepilot/pipeline/audit.py` sanitizes and redacts raw customer chat and contact info, logging only cryptographic hashes, rule IDs, and operational status codes.
