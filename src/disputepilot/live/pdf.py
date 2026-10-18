"""Dependency-free text -> PDF renderer.

Razorpay's Documents API accepts only JPEG, PNG and PDF, so the full rebuttal letter (which is far
longer than the 1000-character contest ``summary`` limit) is uploaded as a PDF.
Uses the built-in Helvetica font, so text must be Latin-1; other characters are replaced with '?'.
"""

from __future__ import annotations

import textwrap

PAGE_W, PAGE_H = 595, 842  # A4 in points
MARGIN = 56
FONT_SIZE = 10
LEADING = 14
MAX_COLS = 92


def _escape(line: str) -> str:
    safe = line.replace("\u20b9", "INR ").encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if not raw.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw, width=MAX_COLS, subsequent_indent="  ") or [""])
    return lines


def text_to_pdf(text: str, title: str = "Dispute rebuttal") -> bytes:
    """Render plain text to a multi-page PDF and return its bytes."""
    lines = _wrap(text)
    per_page = (PAGE_H - 2 * MARGIN) // LEADING
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[""]]

    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    catalog = add("")  # placeholder, patched below
    pages_obj = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    info = add(f"<< /Title ({_escape(title)}) /Producer (DisputePilot) >>")

    kids: list[int] = []
    for page_lines in pages:
        ops = [f"BT /F1 {FONT_SIZE} Tf {LEADING} TL {MARGIN} {PAGE_H - MARGIN} Td"]
        for ln in page_lines:
            ops.append(f"({_escape(ln)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page = add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
        )
        kids.append(page)

    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("latin-1")
    kid_refs = " ".join(f"{k} 0 R" for k in kids)
    objects[pages_obj - 1] = f"<< /Type /Pages /Kids [{kid_refs}] /Count {len(kids)} >>".encode("latin-1")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)
