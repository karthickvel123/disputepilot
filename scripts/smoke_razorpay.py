"""Razorpay test-mode read-only smoke script.

Verifies test credentials by calling list_disputes with count=5.
Makes zero write calls (no accept, no contest, no document upload).
Refuses to run unless RAZORPAY_KEY_ID starts with 'rzp_test_'.
Never prints raw response bodies, authorization headers, or credentials.
"""

import os
import sys

import httpx

# Ensure .env is loaded via disputepilot package
import disputepilot  # noqa: F401
from disputepilot.razorpay.gateway import RazorpayGateway


def run_smoke(
    key_id: str | None = None,
    key_secret: str | None = None,
    client: httpx.Client | None = None,
) -> int:
    """Run read-only dispute listing smoke test against Razorpay test mode.

    Args:
        key_id: Optional Razorpay Key ID (defaults to RAZORPAY_KEY_ID env var).
        key_secret: Optional Razorpay Key Secret (defaults to RAZORPAY_KEY_SECRET env var).
        client: Optional HTTPX client (e.g. mocked client for testing).

    Returns:
        Exit code (0 for success, 1 for failure or refusal).
    """
    resolved_key_id = (
        key_id.strip()
        if key_id is not None
        else (os.environ.get("RAZORPAY_KEY_ID") or "").strip()
    )
    resolved_key_secret = (
        key_secret.strip()
        if key_secret is not None
        else (os.environ.get("RAZORPAY_KEY_SECRET") or "").strip()
    )

    if not resolved_key_id:
        print("Refusing to run: RAZORPAY_KEY_ID is not set.", file=sys.stderr)
        return 1

    if not resolved_key_id.startswith("rzp_test_"):
        print(
            "Refusing to run: RAZORPAY_KEY_ID must start with 'rzp_test_'.",
            file=sys.stderr,
        )
        return 1

    if not resolved_key_secret:
        print("Refusing to run: RAZORPAY_KEY_SECRET is not set.", file=sys.stderr)
        return 1

    gateway = RazorpayGateway(
        key_id=resolved_key_id,
        key_secret=resolved_key_secret,
        client=client,
    )

    try:
        disputes = gateway.list_disputes(count=5)
        http_status = getattr(gateway, "last_status_code", 200) or 200
        print(f"HTTP Status: {http_status}")
        print(f"Disputes Returned: {len(disputes)}")
        if disputes:
            first_dispute = disputes[0]
            if hasattr(first_dispute, "model_dump"):
                field_names = sorted(first_dispute.model_dump().keys())
            elif hasattr(first_dispute, "__dict__"):
                field_names = sorted(first_dispute.__dict__.keys())
            else:
                field_names = []
            print(f"First Dispute Fields: {field_names}")
        return 0

    except httpx.HTTPStatusError as exc:
        print(f"HTTP Status: {exc.response.status_code}")
        print("Disputes Returned: 0")
        return 1
    except Exception as exc:  # noqa: BLE001
        # Never print credentials or full raw payloads
        status = getattr(gateway, "last_status_code", None)
        status_str = str(status) if status is not None else "Error"
        print(f"HTTP Status: {status_str}")
        print("Disputes Returned: 0")
        print(f"Error Type: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke())
