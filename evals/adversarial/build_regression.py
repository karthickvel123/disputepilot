"""Builds evals/adversarial/regression_cases.jsonl: one or more NEW cases per classifier bug fixed.

Written with fresh wording BEFORE measuring, so they test the mechanism, not the original 104 texts.
Extra fields: fix (which fix it guards), must ("answer" = must be answered with `ideal`;
"abstain" = must be routed to a human; "safe" = answering `ideal` or abstaining are both fine, a
different class is not).
"""

import json
from pathlib import Path

INR, NAD, UNA, DUP, SUB, RNR = (
    "item_not_received", "not_as_described", "unauthorised", "duplicate_charge",
    "subscription_cancelled", "refund_not_received",
)
C: list[tuple[str, str, str, str, str]] = [
    # fix, text, ideal, must, note
    ("whole_word", "My brother used my card without asking me", UNA, "safe", "'other' inside 'brother'"),
    ("whole_word", "The seller was otherwise polite but my parcel never arrived", INR, "answer", "'other' inside 'otherwise'"),
    ("whole_word", "Box and seal were unbroken and intact but I was double charged", DUP, "answer", "'broken' inside 'unbroken'"),
    ("whole_word", "The other day my card was used without my permission", UNA, "safe", "bare word 'other' is not a reason"),
    ("whole_word", "Parcel was undelivered for a month", INR, "answer", "inflection/prefix control: 'undelivered' is itself a keyword"),
    ("negation", "Not damaged in any way, but there was no delivery of the second box", INR, "answer", "negated 'damaged'; 'no delivery' still counts"),
    ("negation", "It is no longer defective after the repair, yet I was billed twice", DUP, "answer", "'no longer defective'"),
    ("negation", "Product was not counterfeit, it is genuine, but I was charged twice for it", DUP, "answer", "negated 'counterfeit'"),
    ("negation", "Not only damaged but also missing a part", NAD, "abstain", "'not only' is NOT negation; second issue marker -> human"),
    ("negation", "The item is not faulty. My real complaint is a double charge", DUP, "answer", "negated 'faulty'"),
    ("longest_match", "Customer reports refund not received after cancelling the order", RNR, "answer", "'not received' inside 'refund not received'"),
    ("longest_match", "Goods not received by the buyer", INR, "answer", "'not received' inside 'goods not received' (same class)"),
    ("conflict", "Package missing and also card fraud on my account", INR, "abstain", "two classes + marker"),
    ("conflict", "Item damaged and there was a double charge", NAD, "abstain", "two classes matched"),
    ("conflict", "Subscription cancelled yet a duplicate payment went through", SUB, "abstain", "two classes matched"),
    ("code_mixed", "yeh product fake nikla hai, mera paisa wapas karo", NAD, "safe", "English keyword unreliable in Hinglish"),
    ("code_mixed", "mera order nahi aaya aur bank ne damaged bola", INR, "safe", "mixed language with a stray English keyword"),
    ("inflection", "Items arrived mismatched with the listing", NAD, "answer", "'mismatch' + 'ed'"),
    ("inflection", "Several defects, the goods were damaged on arrival", NAD, "answer", "'damaged' keyword; 'defects' is not a keyword"),
    ("multi_issue", "Item is defective, also I was charged again", NAD, "abstain", "marker 'also' with a keyword"),
    ("multi_issue", "Package missing as well as a wrong invoice", INR, "abstain", "marker 'as well as'"),
    ("spelling_variant", "Customer did not authorise the transaction", UNA, "answer", "British spelling of an existing keyword"),
    ("spelling_variant", "Unrecognised transaction on my statement", UNA, "answer", "British spelling of an existing keyword"),
    ("no_regression", "13.6", RNR, "answer", "exact code unaffected"),
    ("no_regression", "Customer claims refund missing from bank statement", RNR, "answer", "plain keyword unaffected"),
    ("no_regression", "Cardholder was charged twice for a single order", DUP, "answer", "plain keyword unaffected"),
]
out = Path(__file__).with_name("regression_cases.jsonl")
with out.open("w", encoding="utf-8") as f:
    for i, (fix, text, ideal, must, note) in enumerate(C, 1):
        acceptable = [ideal] if must != "abstain" else []
        f.write(json.dumps({"id": f"g{i:03d}", "suite": "reason", "category": f"regression_{fix}", "fix": fix, "text": text,
                            "ideal": ideal if must != "abstain" else "abstain", "acceptable": acceptable, "must": must, "note": note}, ensure_ascii=False) + "\n")
print(f"wrote {len(C)} regression cases -> {out}")
