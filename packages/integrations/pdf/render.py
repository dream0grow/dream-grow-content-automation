"""PDF renderer — converts markdown lead magnets to printable A4 PDF bytes.

Font path is injected (no hardcoded /Users/... path). Returns raw bytes;
caller is responsible for storage.
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

DEFAULT_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
)


def _resolve_font(font_path: str | None) -> str | None:
    candidates = [font_path] if font_path else []
    candidates.extend(DEFAULT_FONT_CANDIDATES)
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def render_lead_magnet_pdf(markdown: str, title: str = "", font_path: str | None = None) -> bytes:
    """Render a lead-magnet markdown to A4 PDF bytes."""
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    resolved = _resolve_font(font_path)
    if resolved:
        pdf.add_font("Body", "", resolved)
        body_font = "Body"
    else:
        body_font = "Helvetica"

    if title:
        pdf.set_font(body_font, size=20)
        pdf.multi_cell(0, 10, title)
        pdf.ln(4)

    pdf.set_font(body_font, size=12)
    for line in _normalize(markdown).split("\n"):
        if not line.strip():
            pdf.ln(3)
            continue
        if line.startswith("# "):
            pdf.set_font(body_font, size=18); pdf.multi_cell(0, 9, line[2:].strip()); pdf.ln(2)
            pdf.set_font(body_font, size=12)
        elif line.startswith("## "):
            pdf.set_font(body_font, size=15); pdf.multi_cell(0, 8, line[3:].strip()); pdf.ln(2)
            pdf.set_font(body_font, size=12)
        elif line.startswith("### "):
            pdf.set_font(body_font, size=13); pdf.multi_cell(0, 7, line[4:].strip()); pdf.ln(1)
            pdf.set_font(body_font, size=12)
        elif line.startswith("- ") or line.startswith("* "):
            pdf.multi_cell(0, 6, "• " + line[2:].strip())
        else:
            pdf.multi_cell(0, 6, line)
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def _normalize(text: str) -> str:
    # strip emphasis markers we don't render
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    return text
