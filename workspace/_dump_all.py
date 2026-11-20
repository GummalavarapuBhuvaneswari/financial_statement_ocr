import json
from pathlib import Path

d = json.loads(Path("output/extracted_financials.json").read_text(encoding="utf-8"))
for i, r in enumerate(d["line_items"], 1):
    print(
        f"{i:02d}. p{r['source_page']} [{r['statement'][:2]}] "
        f"sec={r['section'][:18]:18} | sub={r['subsection'][:22]:22} | "
        f"{'>'*r['indent_level']}{r['line_item'][:50]:50} | "
        f"n={str(r['note_no']):4} | {str(r['fy_2024_25']):>12} | {str(r['fy_2023_24']):>12}"
    )
