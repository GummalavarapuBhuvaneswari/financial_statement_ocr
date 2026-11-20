"""Turn OCR lines into structured financial records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any
from .ocr import OcrLine, OcrWord

NOTE_X = 1280
FY25_X = 1420
FY24_X = 1650

SECTION_HEADERS = {
    "ASSETS",
    "EQUITY AND LIABILITIES",
    "Income",
    "Expenses",
    "Other comprehensive income",
}

SUBSECTION_HINTS = (
    "Non-current assets",
    "Current assets",
    "Equity",
    "Liabilities",
    "Non-current liabilities",
    "Current liabilities",
    "Financial assets",
    "Financial liabilities",
    "Tax expense",
    "Current tax",
    "Items that will not be reclassified",
)


AMOUNT_RE = re.compile(
    r"^\(?-?(?:\d{1,3}(?:,\d{2})*(?:,\d{3})*|\d+)(?:\.\d{1,2})?\)?$"
)
LOOSE_NUM_RE = re.compile(r"^[\(\-]?\d[\d,\.]*\)?\.?$")


@dataclass
class LineItem:
    statement: str
    section: str
    subsection: str
    line_item: str
    note_no: str | None
    fy_2024_25: float | None
    fy_2023_24: float | None
    fy_2024_25_raw: str | None
    fy_2023_24_raw: str | None
    unit: str
    source_page: int
    source_document: str
    extraction_status: str
    ocr_text: str
    bbox: dict
    indent_level: int = 0
    avg_ocr_confidence: float = 0.0
    review_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_amount_token(tok: str) -> str:
    tok = tok.strip().replace(" ", "")
    tok = tok.rstrip(".,;:")
    if re.fullmatch(r"\d+,\d{2}", tok):
        tok = tok.replace(",", ".")
    return tok


def parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s or s in {"-", "—", "–", "=", "_"}:
        return None  
    s = _clean_amount_token(s)
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.startswith("-"):
        negative = True
        s = s[1:]

    # strip Indian thousand separators
    s = s.replace(",", "")
    if not s:
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if negative else val


def _fix_note_token(tok: str) -> str | None:
    """Notes are small integers. Tesseract occasionally invents glyphs like 'T', '&', 'a7'."""
    tok = tok.strip()
    # exact digit
    if re.fullmatch(r"\d{1,2}", tok):
        return tok
    m = re.fullmatch(r"(\d{1,2})[^\d]?", tok)
    if m:
        return m.group(1)
    lookalikes = {"T": "7", "t": "7", "I": "1", "l": "1", "O": "0", "o": "0", "S": "5", "B": "8", "&": "8"}
    if tok in lookalikes:
        return lookalikes[tok]
    letter_as_digit = {
        "a": "3", "A": "3", "e": "9", "E": "9", "g": "9",
        "s": "5", "S": "5", "b": "6", "B": "8", "z": "2", "Z": "2",
    }
    m = re.fullmatch(r"([A-Za-z])(\d{1,2})", tok)
    if m and m.group(1) in letter_as_digit:
        return letter_as_digit[m.group(1)] + m.group(2)

    # "a7" / "E]" style — keep the digit if present
    digits = re.findall(r"\d+", tok)
    if len(digits) == 1 and 1 <= len(digits[0]) <= 2:
        return digits[0]
    return None


def _split_line_by_columns(line: OcrLine) -> tuple[str, str | None, str | None, str | None]:
    """Bucket words into particulars / note / fy25 / fy24 using X coordinates."""
    particulars: list[str] = []
    note_tokens: list[OcrWord] = []
    fy25_tokens: list[OcrWord] = []
    fy24_tokens: list[OcrWord] = []

    for w in line.words:
        x = w.left
        if x >= FY24_X:
            fy24_tokens.append(w)
        elif x >= FY25_X:
            fy25_tokens.append(w)
        elif x >= NOTE_X:
            note_tokens.append(w)
        else:
            particulars.append(w.text)

    note = None
    if note_tokens:
        candidates = sorted(note_tokens, key=lambda w: (len(w.text), -w.conf))
        for c in candidates:
            fixed = _fix_note_token(c.text)
            if fixed:
                note = fixed
                break

    def join_amount(tokens: list[OcrWord]) -> str | None:
        if not tokens:
            return None
        raw = "".join(t.text for t in tokens)
        raw = raw.replace(" ", "")
        if raw.lower() in {"?", "₹", "crore", "2crore", "?crore", "<crore", "ended"}:
            return None
        if re.fullmatch(r"31march20\d{2}", raw.lower()):
            return None
        return raw

    fy25 = join_amount(fy25_tokens)
    fy24 = join_amount(fy24_tokens)

    if fy25 and fy24 is None:
        
        parts = re.findall(r"\(?\d[\d,]*\.?\d*\)?", fy25)
        if len(parts) == 2:
            a, b = parts[0], parts[1]
            if parse_amount(a) is not None and parse_amount(b) is not None:
                fy25, fy24 = a, b

    label = " ".join(particulars).strip()  
    label = re.sub(r"\s+", " ", label)
    label = label.strip(" _")
    return label, note, fy25, fy24


def _looks_like_header_noise(label: str, fy25_raw: str | None = None, fy24_raw: str | None = None) -> bool:
    low = label.lower().strip()
    junk_amount = {None, "", "?", "crore", "?crore", "<crore", "2crore", "ended", "31march2025", "31march2024"}
    if not low:
        a = (fy25_raw or "").lower().replace(" ", "")
        b = (fy24_raw or "").lower().replace(" ", "")
        if a in junk_amount and b in junk_amount:
            return True
        if a.startswith("31march") or b.startswith("31march"):
            return True
        if "crore" in a or "crore" in b:
            return True
        if a == "ended" or b == "ended":
            return True
        if parse_amount(fy25_raw) is not None or parse_amount(fy24_raw) is not None:
            return False
        return True  

    noise = (
        "standalone balance sheet",
        "statement of profit",
        "integrated annual report",
        "particulars",
        "note no",
        "as at",
        "year ended",
        "crore",
    )
    if any(n in low for n in noise) and not any(ch.isdigit() for ch in low):
        return True
    if re.match(r"^(no\.?|na\.?)\b", low):
        return True
    if re.fullmatch(r"[\?\<\₹]?\s*crore", low):
        return True
    return False


def _indent_level(left: int) -> int:
    if left >= 430:
        return 3
    if left >= 390:
        return 2
    if left >= 345:
        return 1
    return 0


def _is_subsection(label: str) -> bool:
    return any(label.lower().startswith(h.lower()) for h in SUBSECTION_HINTS) or label in SUBSECTION_HINTS


def _is_section(label: str) -> bool:
    return label.strip() in SECTION_HEADERS


def detect_statement(page_text: str, page_number: int, line_top: int, page_height: int = 3508) -> str:
    """Page 1 is Balance Sheet. Page 2 starts as Balance Sheet continuation, then flips to P&L."""
    if page_number == 1:
        return "Balance Sheet"
    if "Revenue from operations" in page_text and line_top >= 1250:
        return "Income Statement"
    if line_top >= 1250:
        return "Income Statement"
    return "Balance Sheet"


def parse_page_lines(
    lines: list[OcrLine],
    *,
    source_document: str,
    page_number: int,
    page_full_text: str,
    initial_section: str = "",
    initial_subsection: str = "",
) -> tuple[list[LineItem], str, str]:
    """Return (records, final_section, final_subsection) so multi-page statements keep hierarchy."""
    records: list[LineItem] = []
    section = initial_section
    subsection = initial_subsection
    pending_label = ""

    for line in lines:
        label, note, fy25_raw, fy24_raw = _split_line_by_columns(line)
        if pending_label:
            label = (pending_label + " " + label).strip()
            pending_label = ""

        if _looks_like_header_noise(label, fy25_raw, fy24_raw):
            continue

        # footer page numbers etc.
        if re.match(r"^\d{2,4}\s*\|", label):
            continue

        statement = detect_statement(page_full_text, page_number, line.top)
        if statement == "Income Statement" and section in {
            "ASSETS",
            "EQUITY AND LIABILITIES",
            "",
        }:
            if not _is_section(label):
                pass
            if section in {"ASSETS", "EQUITY AND LIABILITIES"}:
                section = ""
                subsection = ""

        has_amounts = bool(fy25_raw or fy24_raw)

        # section headers
        if _is_section(label) and not has_amounts:
            section = label
            subsection = ""
            continue

        if not has_amounts and not note:
            if label.lower() in {"enterprises", "balances", "plans"} and records:
                records[-1].line_item = (records[-1].line_item + " " + label).strip()
                records[-1].ocr_text = (records[-1].ocr_text + " " + label).strip()
                continue

            if _is_subsection(label) or (label and label[0].isupper() and len(label.split()) <= 5):
                if label in {"Financial assets", "Financial liabilities"}:
                    if subsection in {"Non-current assets", "Current assets", "Non-current liabilities", "Current liabilities"}:
                        subsection = f"{subsection} > {label}"
                    else:
                        subsection = label
                    continue
                if label in {"Current tax"} or _is_subsection(label):
                    subsection = label
                    continue
                if label in {"Liabilities", "Equity"} and not has_amounts:
                    subsection = label
                    continue

            
            if label and not note and not has_amounts:
                if len(label.split()) <= 3 and not label.endswith(":"):
                    pending_label = label
                    continue
                subsection = label
                continue

        # data / total rows
        fy25 = parse_amount(fy25_raw)
        fy24 = parse_amount(fy24_raw)

        status = "Successfully extracted"
        review: list[str] = []

        
        if has_amounts and fy25 is None and fy25_raw not in (None, "-", "—", "–", "=", ""):
            status = "Requires review"
            review.append(f"Could not parse FY 2024-25 token: {fy25_raw!r}")
        if has_amounts and fy24 is None and fy24_raw not in (None, "-", "—", "–", "=", ""):
            status = "Requires review"
            review.append(f"Could not parse FY 2023-24 token: {fy24_raw!r}")
        if line.avg_conf and line.avg_conf < 55:
            status = "Requires review"
            review.append(f"Low OCR confidence ({line.avg_conf:.1f})")
        if not label:
            if fy25 is not None or fy24 is not None:
                label = "(subtotal / amount-only row)"
                review.append("No particulars text on this OCR line — labelled as amount-only subtotal")
                status = "Requires review"
            else:
                status = "Requires review"
                review.append("Missing line-item description")
                label = "[unreadable line item]"

        
        if "exceptional items" in label.lower() and fy25_raw and fy25_raw.startswith("="):
            if fy24 is None and fy25 is not None:
                fy24 = fy25
                fy24_raw = fy25_raw.lstrip("=")
                fy25 = None
                fy25_raw = "-"
                review.append("Re-split exceptional-items dash/value after OCR glue")
                status = "Requires review"

        
        if not section:
            if statement == "Balance Sheet":
                section = "EQUITY AND LIABILITIES" if page_number > 1 else "ASSETS"
            else:
                section = "Income"

        records.append(
            LineItem(
                statement=statement,
                section=section,
                subsection=subsection,
                line_item=label,
                note_no=note,
                fy_2024_25=fy25,
                fy_2023_24=fy24,
                fy_2024_25_raw=fy25_raw if fy25_raw not in (None, "") else ("-" if fy25_raw == "-" else None),
                fy_2023_24_raw=fy24_raw if fy24_raw not in (None, "") else None,
                unit="₹ Crore",
                source_page=page_number,
                source_document=source_document,
                extraction_status=status,
                ocr_text=line.text,
                bbox=line.bbox(),
                indent_level=_indent_level(line.left),
                avg_ocr_confidence=round(line.avg_conf, 2),
                review_notes=review,
            )
        )

    return records, section, subsection
