"""Excel + JSON writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook  # Excel writer
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from .parse import LineItem


EXCEL_COLUMNS = [
    ("Statement", "statement"),
    ("Section", "section"),
    ("Subsection", "subsection"),
    ("Line Item", "line_item"),
    ("Note No.", "note_no"),
    ("FY 2024-25", "fy_2024_25"),
    ("FY 2023-24", "fy_2023_24"),
    ("Unit", "unit"),
    ("Source Page", "source_page"),
    ("Extraction Status", "extraction_status"),
    ("OCR Confidence", "avg_ocr_confidence"),
    ("Review Notes", "review_notes_joined"),
    ("Source Document", "source_document"),
    ("OCR Text", "ocr_text"),
]


def write_excel(records: list[LineItem], path: Path, validation_summary: dict | None = None) -> None:
    wb = Workbook()

    
    ws = wb.active
    ws.title = "Financial Line Items"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="000000", bold=True)
    review_fill = PatternFill("solid", fgColor="FFF2CC")
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    for col, (title, _key) in enumerate(EXCEL_COLUMNS, start=1):
        cell = ws.cell(1, col, title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for row_idx, rec in enumerate(records, start=2):
        payload = rec.to_dict()
        payload["review_notes_joined"] = "; ".join(rec.review_notes)
        for col, (_title, key) in enumerate(EXCEL_COLUMNS, start=1):
            val = payload.get(key)
            cell = ws.cell(row_idx, col, val)
            cell.border = thin
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if key in {"fy_2024_25", "fy_2023_24"} and isinstance(val, (int, float)):
                cell.number_format = "#,##0.00"
            if rec.extraction_status == "Requires review":
                cell.fill = review_fill

    widths = [18, 22, 24, 55, 10, 14, 14, 10, 12, 18, 12, 40, 35, 45]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(EXCEL_COLUMNS))}{len(records) + 1}"

    
    ws2 = wb.create_sheet("Validation Checks")
    ws2.append(["Check", "Severity", "Message", "Related Line Items", "Page"])
    for col in range(1, 6):
        cell = ws2.cell(1, col)
        cell.fill = header_fill
        cell.font = header_font

    if validation_summary:
        for issue in validation_summary.get("issues", []):
            ws2.append(
                [
                    issue.get("check"),
                    issue.get("severity"),
                    issue.get("message"),
                    ", ".join(issue.get("related_line_items") or []),
                    issue.get("page"),
                ]
            )
    for i, w in enumerate([18, 12, 80, 50, 8], start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    
    ws3 = wb.create_sheet("Run Summary")
    ws3.append(["Metric", "Value"])
    ws3["A1"].fill = header_fill
    ws3["B1"].fill = header_fill
    ws3["A1"].font = header_font
    ws3["B1"].font = header_font
    if validation_summary:
        meta = validation_summary.get("run_meta", {})
        for k, v in meta.items():
            
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            ws3.append([k, v])
        ws3.append([])
        ws3.append(["Validation errors", validation_summary.get("errors")])
        ws3.append(["Validation warnings", validation_summary.get("warnings")])
        ws3.append(["Validation info", validation_summary.get("info")])
    ws3.column_dimensions["A"].width = 36
    ws3.column_dimensions["B"].width = 60

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_json(
    records: list[LineItem],
    path: Path,
    *,
    source_document: str,
    validation_summary: dict,
    run_meta: dict[str, Any],
) -> None:
    payload = {
        "document": {
            "filename": source_document,
            "unit": "₹ Crore",
            "reporting_periods": ["FY 2024-25 (as at / year ended 31 March 2025)", "FY 2023-24 (as at / year ended 31 March 2024)"],
        },
        "run": run_meta,
        "validation": {
            "errors": validation_summary.get("errors"),
            "warnings": validation_summary.get("warnings"),
            "info": validation_summary.get("info"),
            "issues": validation_summary.get("issues"),
        },
        "line_items": [r.to_dict() for r in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
