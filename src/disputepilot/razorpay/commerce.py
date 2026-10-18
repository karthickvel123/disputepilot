"""Read-only Razorpay commerce lookups (payment, order, refunds) used to enrich a dispute.

Endpoints (all GET, test or live keys):
  /v1/payments/:id            https://razorpay.com/docs/api/payments/fetch-with-id
  /v1/orders/:id              https://razorpay.com/docs/api/orders/fetch-with-id
  /v1/payments/:id/refunds    https://razorpay.com/docs/api/refunds/fetch-all-for-payment

Razorpay does not hold shipping, courier or invoice data, so those never come from here.
"""

from __future__ import annotations

from typing import Any

from disputepilot.core.models import Order, Refund
from disputepilot.razorpay.gateway import RazorpayGateway


def _notes(entity: dict[str, Any]) -> dict[str, Any]:
    n = entity.get("notes")
    # Razorpay returns [] (not {}) when a payment/order has no notes
    return n if isinstance(n, dict) else {}


class RazorpayCommerceClient:
    """Thin typed wrapper over :meth:`RazorpayGateway.request_json`."""

    def __init__(self, gateway: RazorpayGateway) -> None:
        self.gateway = gateway

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self.gateway.request_json("GET", f"/v1/payments/{payment_id}")

    def fetch_order(self, order_id: str) -> dict[str, Any]:
        return self.gateway.request_json("GET", f"/v1/orders/{order_id}")

    def list_refunds(self, payment_id: str, count: int = 20) -> list[dict[str, Any]]:
        body = self.gateway.request_json("GET", f"/v1/payments/{payment_id}/refunds", params={"count": count})
        items = body.get("items", [])
        return [i for i in items if isinstance(i, dict)]


def order_from_razorpay(payment: dict[str, Any], order: dict[str, Any] | None) -> Order:
    """Build the project's Order model from Razorpay payment/order entities.

    Fields Razorpay does not hold (customer name, shipping address, tracking number, delivery
    time) are read from ``notes`` if the merchant stored them there at order time, else left empty.
    The caller reports which were empty so the UI can show the gap instead of guessing.
    """
    merged_notes = {**_notes(payment), **(_notes(order) if order else {})}
    delivered = merged_notes.get("delivered_at")
    try:
        delivered_at = int(delivered) if delivered not in (None, "") else None
    except (TypeError, ValueError):
        delivered_at = None
    src = order or payment
    return Order(
        id=str((order or {}).get("id") or payment.get("order_id") or payment.get("id") or "unknown"),
        amount=int(src.get("amount") or payment.get("amount") or 0),
        currency=str(src.get("currency") or payment.get("currency") or "INR"),
        status=str((order or {}).get("status") or payment.get("status") or "paid"),
        created_at=int(src.get("created_at") or 0),
        customer_name=str(merged_notes.get("customer_name") or ""),
        customer_email=str(payment.get("email") or ""),
        customer_phone=str(payment.get("contact") or ""),
        shipping_address=str(merged_notes.get("shipping_address") or ""),
        tracking_number=(str(merged_notes["tracking_number"]) if merged_notes.get("tracking_number") else None),
        delivered_at=delivered_at,
    )


def refund_from_razorpay(items: list[dict[str, Any]]) -> Refund | None:
    """Most recent refund for the payment, or None."""
    if not items:
        return None
    latest = max(items, key=lambda r: int(r.get("created_at") or 0))
    arn = None
    data = latest.get("acquirer_data")
    if isinstance(data, dict):
        arn = data.get("arn")
    return Refund(
        id=str(latest.get("id", "")),
        payment_id=str(latest.get("payment_id", "")),
        amount=int(latest.get("amount") or 0),
        currency=str(latest.get("currency") or "INR"),
        status=str(latest.get("status") or "processed"),
        created_at=int(latest.get("created_at") or 0),
        arn=str(arn) if arn else None,
    )
