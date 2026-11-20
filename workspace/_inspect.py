import json
from pathlib import Path

d = json.loads(Path("output/extracted_financials.json").read_text(encoding="utf-8"))
print("rows", len(d["line_items"]))
print("review", d["run"]["line_items_requiring_review"])
print("validation", d["validation"]["errors"], d["validation"]["warnings"], d["validation"]["info"])
print("\n--- key rows ---")
keys = (
    "Property, plant",
    "Total non-current assets",
    "Total current assets",
    "TOTAL ASSETS",
    "Total equity",
    "Total non-current liabilities",
    "Total current liabilities",
    "TOTAL EQUITY AND LIABILITIES",
    "Revenue from operations",
    "Total income",
    "Total expenses",
    "Profit for the year",
    "Total comprehensive income",
    "Exceptional items",
    "Current year",
    "Earlier years",
)
for r in d["line_items"]:
    if any(k.lower() in r["line_item"].lower() for k in keys):
        print(
            f"p{r['source_page']} | {r['statement'][:16]:16} | "
            f"{r['line_item'][:58]:58} | n={str(r['note_no']):4} | "
            f"{r['fy_2024_25']} | {r['fy_2023_24']} | {r['extraction_status']}"
        )

print("\n--- reviews ---")
for r in d["line_items"]:
    if r["extraction_status"] != "Successfully extracted":
        print(r["line_item"], "|", r["review_notes"], "|", r["fy_2024_25_raw"], r["fy_2023_24_raw"])

print("\n--- validation msgs ---")
for i in d["validation"]["issues"]:
    print(f"[{i['severity']}] {i['message']}")
