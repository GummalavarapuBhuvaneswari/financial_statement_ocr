from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ocr_pipeline.pipeline import process_document


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    default_pdf = Path(
    r"C:\Users\bhuva\OneDrive\Desktop\financial_statement_ocr\financial_statement_ocr\input\Scanned Financial Statements.pdf"
    )

    parser = argparse.ArgumentParser(
        description="Extract structured financials from a scanned statement using local Tesseract OCR."
    )
    parser.add_argument(
    "--pdf",
    type=Path,
    default=default_pdf,
    help=f"Path to the scanned financial statement PDF (default: {default_pdf.name})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=here / "output",
        help="Folder for Excel / JSON / report outputs",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=here / "workspace",
        help="Folder for intermediate page images + raw OCR text",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Rasterisation DPI (default 300)")
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"ERROR: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    result = process_document(
        pdf_path=args.pdf,
        output_dir=args.output,
        workspace_dir=args.workspace,
        dpi=args.dpi,
    )

   
    if result["run_meta"]["line_items_extracted"] == 0:
        print("ERROR: no line items extracted.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
