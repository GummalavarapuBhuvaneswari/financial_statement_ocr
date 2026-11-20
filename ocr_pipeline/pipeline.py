
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

from .export import write_excel, write_json
from .images import pdf_to_page_images
from .ocr import configure_tesseract, run_ocr
from .parse import LineItem, parse_page_lines
from .preprocess import preprocess_for_ocr
from .validate import summarise_issues, validate_records


def process_document(
    pdf_path: Path,
    output_dir: Path,
    workspace_dir: Path,
    dpi: int = 300,
) -> dict[str, Any]:
    started = time.perf_counter()
    pdf_path = pdf_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("Financial Statement OCR pipeline")
    print("=" * 64)
    tess = configure_tesseract()
    print(f"Tesseract     : {tess}")
    print(f"Input PDF     : {pdf_path.name}")
    print(f"Output folder : {output_dir}")

    # --- A. render pages ---
    print("\n[1/5] Rendering PDF pages to images ...")
    image_dir = workspace_dir / "page_images"
    try:
        page_images = pdf_to_page_images(pdf_path, image_dir, dpi=dpi)
    except Exception as exc:
        raise RuntimeError(f"Failed to render PDF pages: {exc}") from exc

    pages_ok = 0
    pages_failed: list[dict[str, str]] = []
    all_records: list[LineItem] = []
    raw_text_blobs: dict[int, str] = {}
    carry_section = ""
    carry_subsection = ""

    # --- B/C. preprocess + OCR + parse, page by page so one bad page doesn't kill the run ---
    print("\n[2/5] Preprocessing + OCR + line-item extraction ...")
    for idx, img_path in enumerate(page_images, start=1):
        print(f"\n  -- page {idx} --")
        try:
            debug_path = workspace_dir / "preprocessed" / f"page_{idx}_enhanced.png"
            enhanced = preprocess_for_ocr(img_path, save_debug_to=debug_path)

            full_text, lines = run_ocr(enhanced, page_number=idx)
            raw_path = workspace_dir / "raw_ocr" / f"page_{idx}.txt"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(full_text, encoding="utf-8")
            raw_text_blobs[idx] = full_text

            records, carry_section, carry_subsection = parse_page_lines(
                lines,
                source_document=pdf_path.name,
                page_number=idx,
                page_full_text=full_text,
                initial_section=carry_section,
                initial_subsection=carry_subsection,
            )
            all_records.extend(records)
            # page breaks in this annual report sit after the nested "Financial liabilities"
            # subgroup, so reopen the parent Non-current / Current bucket on the next page
            if " > " in carry_subsection:
                carry_subsection = carry_subsection.split(" > ")[0]
            pages_ok += 1
            print(f"  extracted {len(records)} structured row(s); OCR lines={len(lines)}")
        except Exception as exc:
            pages_failed.append({"page": str(idx), "error": str(exc)})
            print(f"  !! page {idx} failed: {exc}")
            traceback.print_exc()

    # --- D. validation ---
    print("\n[3/5] Running validation / reconciliation checks ...")
    issues = validate_records(all_records)
    validation_summary = summarise_issues(issues)
    print(
        f"  issues: {validation_summary['errors']} error(s), "
        f"{validation_summary['warnings']} warning(s), "
        f"{validation_summary['info']} info"
    )

    elapsed = round(time.perf_counter() - started, 2)
    review_count = sum(1 for r in all_records if r.extraction_status == "Requires review")

    run_meta = {
        "source_document": pdf_path.name,
        "pages_in_document": len(page_images),
        "pages_processed_successfully": pages_ok,
        "pages_failed": pages_failed,
        "line_items_extracted": len(all_records),
        "line_items_requiring_review": review_count,
        "processing_time_seconds": elapsed,
        "ocr_engine": "Tesseract OCR (local, CPU)",
        "unit": "₹ Crore",
        "dpi": dpi,
    }
    validation_summary["run_meta"] = run_meta

    # --- E. exports ---
    print("\n[4/5] Writing Excel + JSON ...")
    excel_path = output_dir / "extracted_financials.xlsx"
    json_path = output_dir / "extracted_financials.json"
    write_excel(all_records, excel_path, validation_summary=validation_summary)
    write_json(
        all_records,
        json_path,
        source_document=pdf_path.name,
        validation_summary=validation_summary,
        run_meta=run_meta,
    )

    # also dump a small human-readable processing report
    report_path = output_dir / "processing_report.txt"
    _write_report(report_path, run_meta, validation_summary, all_records)

    print("\n[5/5] Done.")
    print(f"  Excel  -> {excel_path}")
    print(f"  JSON   -> {json_path}")
    print(f"  Report -> {report_path}")
    print(f"  Time   -> {elapsed}s | pages ok={pages_ok}/{len(page_images)} | rows={len(all_records)} | review={review_count}")

    return {
        "records": all_records,
        "validation": validation_summary,
        "run_meta": run_meta,
        "excel_path": excel_path,
        "json_path": json_path,
    }


def _write_report(path: Path, run_meta: dict, validation_summary: dict, records: list[LineItem]) -> None:
    lines = []
    lines.append("Processing Report — Scanned Financial Statement OCR")
    lines.append("=" * 60)
    for k, v in run_meta.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("Validation summary")
    lines.append("-" * 60)
    lines.append(f"errors   : {validation_summary.get('errors')}")
    lines.append(f"warnings : {validation_summary.get('warnings')}")
    lines.append(f"info     : {validation_summary.get('info')}")
    lines.append("")
    for issue in validation_summary.get("issues", []):
        lines.append(f"[{issue['severity']}] {issue['check']}: {issue['message']}")
    lines.append("")
    lines.append("Line items requiring review")
    lines.append("-" * 60)
    flagged = [r for r in records if r.extraction_status == "Requires review"]
    if not flagged:
        lines.append("(none)")
    for r in flagged:
        lines.append(f"p{r.source_page}: {r.line_item} :: {'; '.join(r.review_notes)}")
    path.write_text("\n".join(lines), encoding="utf-8")
