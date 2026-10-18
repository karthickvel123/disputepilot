"""An in-process fake of the Razorpay HTTP API (httpx.MockTransport) for live-layer tests.

Response shapes follow the public docs: unset evidence categories are JSON null, `others` is a list
of {type, document_ids}, notes are [] when empty, and errors use the {"error": {...}} envelope.
"""

import json
import time
from typing import Any

import httpx

DISPUTE_ID = "disp_LIVE0000000001"
PAYMENT_ID = "pay_LIVE0000000001"
ORDER_ID = "order_LIVE000000001"


def dispute_body(status: str = "open", respond_by: int | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "amount": None, "summary": None, "shipping_proof": None, "billing_proof": None,
        "cancellation_proof": None, "customer_communication": None, "proof_of_service": None,
        "explanation_letter": None, "refund_confirmation": None, "access_activity_log": None,
        "refund_cancellation_policy": None, "term_and_conditions": None, "others": None,
        "submitted_at": None,
    }
    ev.update(evidence or {})
    return {
        "id": DISPUTE_ID, "entity": "dispute", "payment_id": PAYMENT_ID, "amount": 450000,
        "currency": "INR", "amount_deducted": None, "reason_code": "chargeback",
        "reason_description": "Customer says the item was not received",
        "respond_by": respond_by if respond_by is not None else int(time.time()) + 5 * 86400,
        "status": status, "phase": "chargeback", "created_at": int(time.time()) - 86400, "evidence": ev,
    }


class FakeRazorpay:
    """Routes requests, records every write, and lets a test break individual endpoints."""

    def __init__(self, status: str = "open", respond_by: int | None = None) -> None:
        self.status = status
        self.respond_by = respond_by
        self.fail: dict[str, int] = {}  # path prefix -> HTTP status to return
        self.writes: list[tuple[str, str, Any]] = []
        self.doc_counter = 0
        self.disputes_list_calls = 0
        self.evidence: dict[str, Any] = {}

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle), timeout=5.0)

    def _err(self, code: int, text: str) -> httpx.Response:
        return httpx.Response(code, json={"error": {"code": "BAD_REQUEST_ERROR", "description": text}})

    def handle(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        for prefix, code in self.fail.items():
            if path.startswith(prefix):
                return self._err(code, f"forced failure for {prefix}")
        disp = dispute_body(self.status, self.respond_by, self.evidence)

        if req.method == "GET" and path == "/v1/disputes":
            self.disputes_list_calls += 1
            return httpx.Response(200, json={"entity": "collection", "count": 1, "items": [disp]})
        if req.method == "GET" and path == f"/v1/disputes/{DISPUTE_ID}":
            return httpx.Response(200, json=disp)
        if req.method == "GET" and path.startswith("/v1/disputes/"):
            return self._err(400, "The id provided does not exist")
        if req.method == "GET" and path == f"/v1/payments/{PAYMENT_ID}":
            return httpx.Response(200, json={
                "id": PAYMENT_ID, "amount": 450000, "currency": "INR", "status": "captured",
                "order_id": ORDER_ID, "email": "buyer@example.com", "contact": "+919999999999",
                "notes": {"customer_name": "Asha Rao", "tracking_number": "AWB123456"},
                "created_at": int(time.time()) - 10 * 86400,
            })
        if req.method == "GET" and path == f"/v1/orders/{ORDER_ID}":
            return httpx.Response(200, json={
                "id": ORDER_ID, "amount": 450000, "currency": "INR", "status": "paid",
                "notes": [], "created_at": int(time.time()) - 10 * 86400,
            })
        if req.method == "GET" and path == f"/v1/payments/{PAYMENT_ID}/refunds":
            return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})
        if req.method == "POST" and path == "/v1/documents":
            self.doc_counter += 1
            self.writes.append(("POST", path, len(req.content)))
            return httpx.Response(200, json={"id": f"doc_FAKE{self.doc_counter:010d}", "entity": "document"})
        if req.method == "PATCH" and path == f"/v1/disputes/{DISPUTE_ID}/contest":
            body = json.loads(req.content)
            self.writes.append(("PATCH", path, body))
            if body.get("action") == "submit":
                self.status = "under_review"
            return httpx.Response(200, json=dispute_body(self.status, self.respond_by, self.evidence))
        if req.method == "POST" and path == f"/v1/disputes/{DISPUTE_ID}/accept":
            self.writes.append(("POST", path, None))
            self.status = "closed"
            return httpx.Response(200, json=dispute_body(self.status, self.respond_by, self.evidence))
        return httpx.Response(404, json={"error": {"code": "BAD_REQUEST_ERROR", "description": f"unrouted {req.method} {path}"}})
