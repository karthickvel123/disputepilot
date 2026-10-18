"""Condense a rebuttal letter into Razorpay's 1000-character contest ``summary`` field."""

from __future__ import annotations

import re

from disputepilot.razorpay.gateway import CONTEST_SUMMARY_MAX_CHARS

_CITATION = re.compile(r"\s*\[[A-Za-z0-9_\-:.]+\]")


def short_summary(markdown: str, limit: int = CONTEST_SUMMARY_MAX_CHARS) -> str:
    """Return the letter's Summary section as plain sentences, cut on a word boundary to ``limit``.

    The full letter is attached separately as a PDF (explanation_letter), so nothing is lost.
    Only text already present in the verified draft is used - no new claims are introduced.
    """
    lines = markdown.replace("\r\n", "\n").split("\n")
    in_summary = False
    sentences: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("## "):
            if in_summary:
                break
            in_summary = stripped[3:].strip().lower().startswith("summary")
            continue
        if in_summary and stripped.startswith("- "):
            sentences.append(_CITATION.sub("", stripped[2:]).strip())
    text = " ".join(s for s in sentences if s)
    if not text:  # draft without a Summary section: fall back to the first prose lines
        body = [re.sub(r"^[-# *\t]+|[-# *\t]+$", "", ln) for ln in lines if ln.strip() and not ln.startswith("#")]
        text = _CITATION.sub("", " ".join(body))

    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "\u2026"
