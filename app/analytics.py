"""Analytics layer: deterministic, parameterized SQL queries.

Every function returns the same shape:
    {"intent": str, "answer": str, "data": [ {col: value}, ... ], "sql": str, "params": dict}
The LLM never writes SQL; it can only choose one of the functions in INTENTS below.
"""
import sqlite3
from datetime import datetime

from app.database import get_connection

# Business definition of revenue (documented in the README):
#   revenue = quantity * unit_price - discount_amount, for Completed orders only.
REVENUE_EXPR = "(quantity * unit_price - discount_amount)"
VALID_ROWS = "status = 'Completed'"


class AnalyticsError(Exception):
    """Raised when a question can't be answered from the data (bad month, no data...)."""


def _run(sql, params=None, db_path=None):
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        rows = conn.execute(sql, params or {}).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _money(value):
    return f"{value:,.2f}"


def _month_label(month):
    """'2026-03' -> 'March 2026'"""
    return datetime.strptime(month, "%Y-%m").strftime("%B %Y")


def available_months(db_path=None):
    rows = _run(f"SELECT DISTINCT order_month FROM sales WHERE {VALID_ROWS} ORDER BY order_month", db_path=db_path)
    return [r["order_month"] for r in rows]


def total_revenue(db_path=None):
    sql = f"""SELECT ROUND(SUM({REVENUE_EXPR}), 2) AS total_revenue,
                     COUNT(*) AS completed_orders
              FROM sales WHERE {VALID_ROWS}"""
    rows = _run(sql, db_path=db_path)
    if not rows or rows[0]["total_revenue"] is None:
        raise AnalyticsError("There are no completed sales in the database.")
    r = rows[0]
    return {"intent": "total_revenue",
            "answer": f"Total revenue is {_money(r['total_revenue'])} from {r['completed_orders']} completed orders.",
            "data": rows, "sql": " ".join(sql.split()), "params": {}}


def top_product(db_path=None):
    sql = f"""SELECT product, ROUND(SUM({REVENUE_EXPR}), 2) AS revenue,
                     SUM(quantity) AS units_sold
              FROM sales WHERE {VALID_ROWS}
              GROUP BY product ORDER BY revenue DESC, product ASC"""
    rows = _run(sql, db_path=db_path)
    if not rows:
        raise AnalyticsError("There are no completed sales in the database.")
    best = rows[0]
    return {"intent": "top_product",
            "answer": f"{best['product']} generated the highest revenue: {_money(best['revenue'])}.",
            "data": rows, "sql": " ".join(sql.split()), "params": {}}


def top_region(db_path=None):
    sql = f"""SELECT region, ROUND(SUM({REVENUE_EXPR}), 2) AS revenue,
                     COUNT(*) AS orders
              FROM sales WHERE {VALID_ROWS}
              GROUP BY region ORDER BY revenue DESC, region ASC"""
    rows = _run(sql, db_path=db_path)
    if not rows:
        raise AnalyticsError("There are no completed sales in the database.")
    best = rows[0]
    return {"intent": "top_region",
            "answer": f"The {best['region']} region generated the highest sales: {_money(best['revenue'])}.",
            "data": rows, "sql": " ".join(sql.split()), "params": {}}


def monthly_trend(db_path=None):
    sql = f"""SELECT order_month AS month, ROUND(SUM({REVENUE_EXPR}), 2) AS revenue
              FROM sales WHERE {VALID_ROWS}
              GROUP BY order_month ORDER BY order_month"""
    rows = _run(sql, db_path=db_path)
    if not rows:
        raise AnalyticsError("There are no completed sales in the database.")
    first, last = rows[0], rows[-1]
    peak = max(rows, key=lambda r: r["revenue"])
    answer = (f"Monthly revenue went from {_money(first['revenue'])} in {_month_label(first['month'])} "
              f"to {_money(last['revenue'])} in {_month_label(last['month'])}. "
              f"The peak month was {_month_label(peak['month'])} ({_money(peak['revenue'])}).")
    return {"intent": "monthly_trend", "answer": answer,
            "data": rows, "sql": " ".join(sql.split()), "params": {}}


def revenue_change(month_a, month_b, db_path=None):
    """Revenue change from month_a to month_b (both 'YYYY-MM')."""
    months = available_months(db_path)
    for m in (month_a, month_b):
        if m not in months:
            raise AnalyticsError(
                f"No data for month '{m}'. Available months: {', '.join(months)}.")
    if month_a == month_b:
        raise AnalyticsError("Please choose two different months to compare.")

    sql = f"""SELECT order_month AS month, ROUND(SUM({REVENUE_EXPR}), 2) AS revenue
              FROM sales WHERE {VALID_ROWS} AND order_month IN (:a, :b)
              GROUP BY order_month"""
    rows = _run(sql, {"a": month_a, "b": month_b}, db_path)
    rev = {r["month"]: r["revenue"] for r in rows}
    a, b = rev[month_a], rev[month_b]
    diff = round(b - a, 2)
    pct = round(diff / a * 100, 2) if a else None
    direction = "increased" if diff > 0 else "decreased" if diff < 0 else "did not change"
    pct_text = f" ({pct:+.2f}%)" if pct is not None else ""
    answer = (f"Revenue {direction} from {_money(a)} in {_month_label(month_a)} "
              f"to {_money(b)} in {_month_label(month_b)}: a change of {diff:+,.2f}{pct_text}.")
    data = [{"month": month_a, "revenue": a},
            {"month": month_b, "revenue": b},
            {"month": "change", "revenue": diff, "percent_change": pct}]
    return {"intent": "revenue_change", "answer": answer, "data": data,
            "sql": " ".join(sql.split()), "params": {"a": month_a, "b": month_b}}


# Allowlist of supported intents -> (function, required parameter names).
# The AI layer may ONLY pick from this dictionary.
INTENTS = {
    "total_revenue": (total_revenue, []),
    "top_product": (top_product, []),
    "top_region": (top_region, []),
    "monthly_trend": (monthly_trend, []),
    "revenue_change": (revenue_change, ["month_a", "month_b"]),
}


def run_intent(intent, params=None, db_path=None):
    if intent not in INTENTS:
        raise AnalyticsError(f"Unsupported intent: {intent}")
    func, required = INTENTS[intent]
    params = params or {}
    missing = [p for p in required if p not in params]
    if missing:
        raise AnalyticsError(f"Missing parameter(s): {', '.join(missing)}")
    return func(**{p: params[p] for p in required}, db_path=db_path)
