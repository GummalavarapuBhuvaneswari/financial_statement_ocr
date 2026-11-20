"""Validation / reconciliation checks."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

from .parse import LineItem


@dataclass
class ValidationIssue:
    check: str
    severity: str  
    message: str
    related_line_items: list[str]
    page: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _find(records: Iterable[LineItem], name_substr: str, statement: str | None = None) -> LineItem | None:
    """Prefer an exact / startswith hit so 'total assets' does not grab 'total non-current assets'."""
    needle = _norm(name_substr)
    candidates = []
    for r in records:
        if statement and r.statement != statement:
            continue
        label = _norm(r.line_item)
        if label == needle or label.startswith(needle + " ") or needle == label:
            candidates.append((0, r))  
        elif needle in label:
            candidates.append((1, r))  
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _near(a: float | None, b: float | None, tol: float = 0.05) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def validate_records(records: list[LineItem]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # 1) missing / unreadable values on rows that look like they should have numbers
    for r in records:
        looks_like_total = "total" in r.line_item.lower()
        looks_like_leaf = r.note_no is not None or looks_like_total
        if looks_like_leaf and r.fy_2024_25 is None and r.fy_2023_24 is None:
            if not (
                (r.fy_2024_25_raw in {None, "-"})
                and (r.fy_2023_24_raw in {None, "-"} or r.fy_2023_24 is not None)
            ):
                issues.append(
                    ValidationIssue(
                        check="missing_values",
                        severity="warning",
                        message=f"No usable amounts for '{r.line_item}'",
                        related_line_items=[r.line_item],
                        page=r.source_page,
                    )
                )
        if r.extraction_status == "Requires review":
            issues.append(
                ValidationIssue(
                    check="extraction_status",
                    severity="warning",
                    message=f"Flagged for review: {r.line_item} ({'; '.join(r.review_notes) or 'see record'})",
                    related_line_items=[r.line_item],
                    page=r.source_page,
                )
            )

    
    bs = [r for r in records if r.statement == "Balance Sheet"]

    def check_sum(children: list[str], total_name: str, year_attr: str, label: str):
        total = _find(bs, total_name, "Balance Sheet")
        if not total:
            return
        parts = []
        for c in children:
            hit = _find(bs, c, "Balance Sheet")
            if hit:
                parts.append(hit)
        if len(parts) < len(children):
            return
        summed = 0.0
        ok = True
        for p in parts:
            val = getattr(p, year_attr)
            raw = getattr(p, year_attr + "_raw")
            if val is None and raw in {"-", "—", "–", "=", None, ""}:
                val = 0.0
            if val is None:
                ok = False
                break
            summed += val
        total_val = getattr(total, year_attr)
        if not ok or total_val is None:
            issues.append(
                ValidationIssue(
                    check="arithmetic",
                    severity="warning",
                    message=f"Could not fully reconcile {label} ({year_attr}) — missing component value(s)",
                    related_line_items=[total.line_item] + [p.line_item for p in parts],
                    page=total.source_page,
                )
            )
            return
        if not _near(summed, total_val, tol=1.0):
            issues.append(
                ValidationIssue(
                    check="arithmetic",
                    severity="error",
                    message=(
                        f"{label} mismatch on {year_attr}: components sum to {summed:.2f} "
                        f"but extracted total is {total_val:.2f}"
                    ),
                    related_line_items=[total.line_item] + [p.line_item for p in parts],
                    page=total.source_page,
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    check="arithmetic",
                    severity="info",
                    message=f"{label} reconciles on {year_attr} ({total_val:.2f})",
                    related_line_items=[total.line_item],
                    page=total.source_page,
                )
            )

    
    for year in ("fy_2024_25", "fy_2023_24"):
        check_sum(
            [
                "total non-current assets",
                "total current assets",
                "assets held for sale",
                "regulatory deferral account debit",
            ],
            "total assets",
            year,
            "TOTAL ASSETS",
        )
        check_sum(
            [
                "total equity",
                "total non-current liabilities",
                "total current liabilities",
                "deferred revenue",
                "regulatory deferral account credit",
            ],
            "total equity and liabilities",
            year,
            "TOTAL EQUITY AND LIABILITIES",
        )

   
    for year, nice in (("fy_2024_25", "FY 2024-25"), ("fy_2023_24", "FY 2023-24")):
        assets = _find(bs, "total assets", "Balance Sheet")
        equity = _find(bs, "total equity and liabilities", "Balance Sheet")
        if assets and equity:
            a = getattr(assets, year)
            e = getattr(equity, year)
            if a is not None and e is not None:
                if _near(a, e, tol=0.05):
                    issues.append(
                        ValidationIssue(
                            check="balance_sheet_identity",
                            severity="info",
                            message=f"Assets equal Equity & Liabilities for {nice} ({a:.2f})",
                            related_line_items=[assets.line_item, equity.line_item],
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            check="balance_sheet_identity",
                            severity="error",
                            message=f"Assets ({a:.2f}) != Equity & Liabilities ({e:.2f}) for {nice}",
                            related_line_items=[assets.line_item, equity.line_item],
                        )
                    )

   
    pl = [r for r in records if r.statement == "Income Statement"]
    for year in ("fy_2024_25", "fy_2023_24"):
        income = _find(pl, "total income", "Income Statement")
        expenses = _find(pl, "total expenses", "Income Statement")
        profit = _find(pl, "profit before exceptional items", "Income Statement")
        if income and expenses and profit:
            i = getattr(income, year)
            e = getattr(expenses, year)
            p = getattr(profit, year)
            if None not in (i, e, p):
                if _near(i - e, p, tol=1.0):
                    issues.append(
                        ValidationIssue(
                            check="arithmetic",
                            severity="info",
                            message=f"Income - Expenses reconciles to profit-before-exceptional on {year}",
                            related_line_items=[income.line_item, expenses.line_item, profit.line_item],
                        )
                    )
                else:
                    issues.append(
                        ValidationIssue(
                            check="arithmetic",
                            severity="error",
                            message=(
                                f"Income ({i:.2f}) - Expenses ({e:.2f}) = {i - e:.2f}, "
                                f"but extracted profit-before-exceptional is {p:.2f}"
                            ),
                            related_line_items=[income.line_item, expenses.line_item, profit.line_item],
                        )
                    )

    return issues


def summarise_issues(issues: list[ValidationIssue]) -> dict:
    return {
        "total_issues": len(issues),
        "errors": sum(1 for i in issues if i.severity == "error"),
        "warnings": sum(1 for i in issues if i.severity == "warning"),
        "info": sum(1 for i in issues if i.severity == "info"),
        "issues": [i.to_dict() for i in issues],
    }
