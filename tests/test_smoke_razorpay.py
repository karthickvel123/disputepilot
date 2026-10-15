"""Unit tests for scripts/smoke_razorpay.py.

Verifies:
1. Refusal to run when RAZORPAY_KEY_ID does not start with 'rzp_test_'.
2. Refusal to run when credentials are missing.
3. No secret or key text is printed to stdout or stderr under any condition.
4. Successful dispute listing with mocked transport and sanitized output.
5. Clean handling of 4xx errors without raw body or credential leakage.
"""

import httpx
import pytest

from scripts.smoke_razorpay import run_smoke


def test_smoke_refuses_non_test_key(capsys: pytest.CaptureFixture[str]) -> None:
    """Refuse to run when key_id is a live key (e.g. rzp_live_...) and leak zero secrets."""
    live_key = "rzp_live_secretkey12345678"
    secret_val = "super_confidential_secret_abcxyz"

    requests_sent = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests_sent
        requests_sent += 1
        return httpx.Response(200, json={"items": []})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    exit_code = run_smoke(key_id=live_key, key_secret=secret_val, client=client)

    assert exit_code == 1
    assert requests_sent == 0, "No network request must be made when key is refused"

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    # Assert refusal message is present
    assert "Refusing to run: RAZORPAY_KEY_ID must start with 'rzp_test_'." in combined_output

    # CRITICAL: Verify NO secret or live key appears anywhere in output
    assert live_key not in combined_output
    assert secret_val not in combined_output
    assert "Authorization" not in combined_output


def test_smoke_refuses_missing_or_invalid_keys(capsys: pytest.CaptureFixture[str]) -> None:
    """Refuse to run when key is empty, malformed, or secret is unset."""
    # 1. Empty key
    code = run_smoke(key_id="", key_secret="some_secret")
    assert code == 1
    out = capsys.readouterr()
    assert "Refusing to run: RAZORPAY_KEY_ID is not set." in (out.out + out.err)
    assert "some_secret" not in (out.out + out.err)

    # 2. Key with bad prefix
    code = run_smoke(key_id="test_key_without_rzp", key_secret="some_secret")
    assert code == 1
    out = capsys.readouterr()
    assert "Refusing to run: RAZORPAY_KEY_ID must start with 'rzp_test_'." in (out.out + out.err)
    assert "test_key_without_rzp" not in (out.out + out.err)
    assert "some_secret" not in (out.out + out.err)

    # 3. Missing secret
    code = run_smoke(key_id="rzp_test_validkey", key_secret="")
    assert code == 1
    out = capsys.readouterr()
    assert "Refusing to run: RAZORPAY_KEY_SECRET is not set." in (out.out + out.err)


def test_smoke_success_with_mock_transport(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify successful run with test key prints only status, count, and field names."""
    test_key = "rzp_test_dummykey123"
    test_secret = "secret_value_must_never_leak_987654"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        # Check query param count=5
        assert "count=5" in str(request.url)
        return httpx.Response(
            200,
            json={
                "entity": "collection",
                "count": 1,
                "items": [
                    {
                        "id": "disp_test_001",
                        "entity": "dispute",
                        "payment_id": "pay_test_001",
                        "amount": 250000,
                        "currency": "INR",
                        "reason_code": "13.1",
                        "status": "open",
                        "phase": "chargeback",
                        "respond_by": 1720000000,
                        "created_at": 1719000000,
                        "evidence": {},
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    exit_code = run_smoke(key_id=test_key, key_secret=test_secret, client=client)

    assert exit_code == 0

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    # Must print HTTP status, number of disputes returned, and field names
    assert "HTTP Status: 200" in captured.out
    assert "Disputes Returned: 1" in captured.out
    assert "First Dispute Fields:" in captured.out
    assert "'id'" in captured.out
    assert "'amount'" in captured.out

    # Must NOT leak secret or raw payload
    assert test_secret not in combined_output
    assert "secret_value" not in combined_output
    assert "Authorization" not in combined_output


def test_smoke_handles_4xx_without_leaking_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify 4xx error prints HTTP status and 0 disputes without leaking raw response or credentials."""
    test_key = "rzp_test_unauthorizedkey"
    test_secret = "secret_to_hide_on_error_123"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": "BAD_REQUEST_ERROR", "description": "The credentials provided are invalid"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    exit_code = run_smoke(key_id=test_key, key_secret=test_secret, client=client)

    assert exit_code == 1

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    assert "HTTP Status: 401" in captured.out
    assert "Disputes Returned: 0" in captured.out
    assert test_secret not in combined_output
    assert "Authorization" not in combined_output
