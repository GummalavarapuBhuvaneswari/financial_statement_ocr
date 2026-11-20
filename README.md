# Scanned Financial Statement — OCR, Extraction & Validation

Python pipeline that reads the supplied scanned financial statement PDF, runs **local Tesseract OCR** on each page (CPU only), extracts structured Balance Sheet / Income Statement line items, validates arithmetic relationships, and writes **Excel + JSON** outputs with full source traceability.

---

## What it does

1. Renders each PDF page to a high-DPI PNG (PyMuPDF).
2. Preprocesses the image (denoise + CLAHE contrast).
3. Runs **Tesseract OCR** locally via `pytesseract` and keeps word bounding boxes.
4. Reconstructs each financial row using column X-positions:
   `Particulars | Note No. | FY 2024-25 | FY 2023-24`
5. Preserves section / subsection hierarchy from indentation and header rows.
6. Validates totals (Assets identity, Income − Expenses, etc.) — **flags mismatches, never silently “fixes” numbers**.
7. Emits:
   - `output/extracted_financials.xlsx`
   - `output/extracted_financials.json`
   - `output/processing_report.txt`

---

## Prerequisites

| Dependency | Why |
|---|---|
| Python 3.10+ | runtime |
| [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Windows build is fine) | mandatory local OCR engine |
| English traineddata (`eng.traineddata`) | usually bundled with the installer |

If `tesseract` is not on `PATH`, either add it or set:

```bat
set TESSERACT_CMD=C:\Users\<you>\AppData\Local\Programs\Tesseract-OCR\tesseract.exe
```

---

## Setup

```bat
cd financial_statement_ocr
python -m pip install -r requirements.txt
```

Confirm Tesseract is visible:

```bat
tesseract --version
```

---

## Run

From the `financial_statement_ocr` folder (default PDF path points one level up to `input/Scanned Financial Statements.pdf`):

```bat
python run.py
```

Or pass an explicit PDF:

```bat
python run.py --pdf "..input/Scanned Financial Statements.pdf" --output output --dpi 300
```

### CLI options

| Flag | Default | Meaning |
|---|---|---|
| `--pdf` | `..input/Scanned Financial Statements.pdf` | input scan |
| `--output` | `./output` | Excel / JSON / report |
| `--workspace` | `./workspace` | intermediate images + raw OCR text |
| `--dpi` | `300` | rasterisation resolution |

---

## Outputs

### Excel (`extracted_financials.xlsx`)

Sheets:

1. **Financial Line Items** — one row per extracted line, columns include Statement, Section, Subsection, Line Item, Note No., FY 2024-25, FY 2023-24, Unit, Source Page, Extraction Status, OCR Confidence, Review Notes, Source Document, OCR Text.
2. **Validation Checks** — reconciliation / missing-value / review flags.
3. **Run Summary** — pages processed, timing, counts.

Rows marked **Requires review** are highlighted in yellow.

### JSON (`extracted_financials.json`)

Machine-readable payload with:

- document metadata
- run metrics (timing, pages ok/failed, review count)
- validation issues
- every line item including hierarchy, values, OCR text, bounding box and source page

### Workspace (debug)

- `workspace/page_images/page_N.png` — rendered pages
- `workspace/preprocessed/page_N_enhanced.png` — images fed to Tesseract
- `workspace/raw_ocr/page_N.txt` — raw OCR text dump

---

## Project layout

```
financial_statement_ocr/
├── input/
│   ├── Scanned Financial Statements.pdf
├── run.py                      # CLI entry
├── requirements.txt
├── README.md
├── TECHNICAL_NOTE.md
├── ocr_pipeline/
│   ├── images.py               # PDF → images
│   ├── preprocess.py           # denoise / CLAHE
│   ├── ocr.py                  # Tesseract wrapper + word boxes
│   ├── parse.py                # line-item / hierarchy extraction
│   ├── validate.py             # reconciliation checks
│   ├── export.py               # Excel + JSON
│   └── pipeline.py             # orchestration
└── output/                     # generated artefacts
```

---

## Processing constraints (honoured)

- Python implementation
- Tesseract OCR via `pytesseract`
- CPU-only, local processing
- No cloud OCR, no external OCR APIs, no GPU requirement

---

## Note on page count

The assignment brief mentions a three-page statement. The supplied file
`Scanned Financial Statements.pdf` contains **2 pages**:

1. Standalone Balance Sheet (Assets + start of Equity & Liabilities)
2. Balance Sheet continuation + Statement of Profit and Loss

The pipeline processes **all pages present** in the PDF and records that count in the run summary.

---

## Demonstration

```bat
cd financial_statement_ocr
python run.py
```

Expected console ending:

```
[5/5] Done.
  Excel  -> ...\output\extracted_financials.xlsx
  JSON   -> ...\output\extracted_financials.json
  Report -> ...\output\processing_report.txt
  Time   -> Ns | pages ok=2/2 | rows=... | review=...
```
