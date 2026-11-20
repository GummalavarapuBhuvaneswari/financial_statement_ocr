# Technical Note — Scanned Financial Statement OCR Pipeline

## 1. OCR and image preprocessing

**PDF → image.** Each page is rasterised at 300 DPI with PyMuPDF. That gives Tesseract enough pixels for thin table rules and Indian-format commas without needing a separate Poppler install on Windows.

**Preprocessing (OpenCV, CPU):**
1. Convert to greyscale.
2. `fastNlMeansDenoising` — knocks out scanner speckles without blurring digits.
3. CLAHE (clipLimit 2.0, 8×8 tiles) — lifts contrast on the pale grey total-rows so text does not dissolve into the background.

I deliberately avoided aggressive binarisation / morphological opens. On this particular scan, hard thresholding started deleting the comma separators inside large amounts (`2,10,927.53`). Greyscale + CLAHE was the more stable choice.

**OCR engine.** Local Tesseract 5 (`--oem 3 --psm 6`) through `pytesseract`. PSM 6 (“assume a uniform block of text”) worked best for these ruled tables. I also keep `image_to_data` word boxes so every token still has an `(x, y, w, h, conf)` — that is what drives column splitting and source traceability.

---

## 2. How financial line items and numerical columns were identified

The statement layout is four logical columns:

| Zone | Approx. X at 300 DPI | Content |
|---|---|---|
| Particulars | &lt; 1280 | line-item description |
| Note No. | 1280 – 1420 | small integer note reference |
| FY 2024-25 | 1420 – 1650 | current period amount |
| FY 2023-24 | ≥ 1650 | comparative amount |

For each OCR line I bucket words by their `left` coordinate into those four zones, then:

- reassemble the particulars text in reading order
- normalise the note token (OCR sometimes returns `T`/`&`/`a7` instead of `7`/`8`/`37` — I recover the digit when it is unambiguous and still flag low-confidence cases)
- parse amounts with Indian thousand separators (`2,10,927.53`), parentheses for negatives (`(445.02)`), and dash/blank for empty cells
- **never coerce a dash into `0.00`** — blanks stay blank so validation can tell “missing” from “zero”

Wrapped descriptions (e.g. the Trade-payables “enterprises” continuation) are stitched back onto the previous row.

Statement type is inferred from page context: page 1 is Balance Sheet; on page 2 the pipeline switches to Income Statement once the vertical position / content crosses into the P&amp;L block (`Revenue from operations`, etc.).

---

## 3. How hierarchical relationships were maintained

Hierarchy is reconstructed, not guessed from fonts (OCR does not reliably return bold):

1. **Section** headers (`ASSETS`, `EQUITY AND LIABILITIES`, `Income`, `Expenses`, `Other comprehensive income`) update a running `section` state and clear the subsection.
2. **Subsection** labels (`Non-current assets`, `Financial assets`, `Current liabilities`, `Tax expense`, …) update `subsection` without emitting an amount row.
3. Data / total rows inherit the current section + subsection.
4. Indentation (word `left` position) is stored as `indent_level` (0–3) so the original nesting depth survives into Excel/JSON even if a reviewer later edits the text.

Ordering of rows is the original top-to-bottom OCR order, so parent totals still appear after their children.

---

## 4. Validation and reconciliation

Checks implemented in `validate.py`:

1. **Missing / unreadable values** on rows that look like they should carry amounts.
2. **Extraction-status propagation** — anything already marked `Requires review` (parse failure, low confidence, glued tokens) shows up in the validation sheet.
3. **Arithmetic relationships**
   - `TOTAL ASSETS ≈ Total non-current + Total current + Assets held for sale + Regulatory debit balances`
   - `TOTAL EQUITY AND LIABILITIES ≈ Total equity + Total non-current liabilities + Total current liabilities + Deferred revenue + Regulatory credit balances`
   - `Total income − Total expenses ≈ Profit before exceptional items…`
4. **Balance-sheet identity** — Assets must equal Equity & Liabilities for each year.

Failures are recorded as `error` / `warning` / `info`. Extracted numbers are **not** rewritten to force a reconcile — that matches the assignment rule *“Do not silently modify extracted values to make totals reconcile.”*

---

## 5. Source traceability

Every line item carries:

- original document filename
- source page number
- original OCR line text
- bounding box (`left/top/right/bottom` in page-image pixels)
- average OCR confidence
- raw amount tokens before parsing

These fields travel into both Excel and JSON, so a later review/correction can always point back to the exact place on the scan.

---

## 6. Known limitations and improvements

1. **Page count.** The brief describes three pages; the supplied PDF has two. The pipeline processes whatever pages exist and reports the count.
2. **Note-number OCR noise.** Small note glyphs are the weakest part of the scan (`7→T`, `8→&`, `37→a7`). Heuristic recovery helps, but anything ambiguous is marked for review rather than guessed aggressively.
3. **Header / unit glyphs.** The ₹ symbol often becomes `?` / `<` / `2`. Harmless because the unit is known (`₹ Crore`) and injected into every record.
4. **Multi-line particulars.** Most wraps are handled; unusually broken lines may still need a manual join (they show up under review notes).
5. **Column cut-offs are layout-specific.** The X thresholds were tuned on this 300 DPI render. A differently cropped scan would need a short recalibration (or a header-row detector that learns the cuts automatically).
6. **Natural next steps:** header-row based dynamic column detection, confidence-weighted digit correction using a language model over the note column only, and a small interactive review UI that overlays boxes on the page image.

---

## 7. Major dependencies (and why)

| Library | Purpose |
|---|---|
| `pymupdf` | Local PDF page rendering without Poppler |
| `pytesseract` | Official-style wrapper around local Tesseract |
| `opencv-python-headless` | Denoise + CLAHE preprocessing on CPU |
| `numpy` | Array backbone for OpenCV |
| `Pillow` | Image helpers |
| `openpyxl` | Structured Excel workbook output |

Tesseract itself is an external system binary; Python never shells out to a cloud OCR service.
