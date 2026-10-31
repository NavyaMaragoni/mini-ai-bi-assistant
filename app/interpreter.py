"""Interpreter: turns a natural-language question into (intent, params).

This is the rule-based interpreter. It needs no API key, is fully deterministic,
and is the fallback when the LLM is unavailable (added in Step 5).

It never produces SQL. It can only choose an intent from the allowlist in
app.analytics.INTENTS, and it refuses questions it cannot answer correctly.
"""
import re

from app.analytics import _run, available_months

SUPPORTED_EXAMPLES = [
    "What is the total revenue?",
    "Which product generated the highest revenue?",
    "What is the monthly revenue trend?",
    "Which region generated the highest sales?",
    "How did revenue change between February and March?",
]


class UnsupportedQuestion(Exception):
    """The question is outside what this assistant can answer correctly."""


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b")
ISO_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")
YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Things we deliberately do NOT support. Refusing is better than a wrong answer
# (e.g. answering "lowest revenue region" with the highest one).
UNSUPPORTED_RE = re.compile(
    r"\b(lowest|least|worst|bottom|minimum|smallest|category|categories|channel|channels|"
    r"online|retail|profit|profits|margin|margins|forecast|predict|prediction|customer|"
    r"customers|cost|costs|discount|discounts|return|returns|returned|refund|refunds|"
    r"average|avg|quarter|quarterly|week|weekly|daily|day|yearly|year)\b")

# Input that looks like a database command is refused outright. (We never execute
# user text as SQL anyway; this just gives a clear message instead of a wrong answer.)
SQL_LIKE_RE = re.compile(
    r"\b(drop|delete|insert|update|alter|truncate|create|select|union|pragma|attach)\b|;|--")

CHANGE_RE = re.compile(
    r"\b(change|changed|compare|compared|comparison|difference|versus|vs|growth|grew|"
    r"increase|increased|decrease|decreased)\b")
TREND_RE = re.compile(r"\b(trend|monthly|month-wise|monthwise|month by month|over time|each month|per month|by month)\b")
MEASURE_RE = re.compile(r"\b(revenue|sales|highest|top|best|most|generated|performing|performs|earned|sold)\b")
REGION_RE = re.compile(r"\b(region|regions)\b")
PRODUCT_RE = re.compile(r"\b(product|products|item|items)\b")
REVENUE_RE = re.compile(r"\b(revenue|sales)\b")
TOTAL_RE = re.compile(r"\b(total|overall|altogether|in all|how much)\b")
GROUPING_RE = re.compile(r"\b(by|per|each|every)\b")


def _known_entities():
    """Region and product names present in the data (lowercased)."""
    rows = _run("SELECT DISTINCT product AS name FROM sales UNION SELECT DISTINCT region FROM sales")
    return [r["name"].lower() for r in rows]


def _find_months(q):
    """Return the months mentioned in the question as 'YYYY-MM', in order of mention."""
    available = available_months()
    found = [(m.start(), f"{m.group(1)}-{m.group(2)}") for m in ISO_RE.finditer(q)]

    text_wo_iso = ISO_RE.sub(" ", q)
    years = set(YEAR_RE.findall(text_wo_iso))
    for m in MONTH_RE.finditer(text_wo_iso):
        num = MONTHS[m.group(1)[:3]]
        if len(years) == 1:
            year = next(iter(years))
        else:
            candidates = [a for a in available if a.endswith(f"-{num:02d}")]
            if len(candidates) == 1:
                year = candidates[0][:4]
            elif not candidates and available:
                year = available[-1][:4]      # no data for that month; analytics reports it
            else:
                raise UnsupportedQuestion("Please include the year (e.g. 'March 2026').")
        found.append((m.start(), f"{year}-{num:02d}"))

    return [month for _, month in sorted(found)]


def interpret(question):
    """Return {"intent": str, "params": dict, "interpreter": "rules"} or raise UnsupportedQuestion."""
    q = " ".join(question.lower().split())

    if SQL_LIKE_RE.search(q):
        raise UnsupportedQuestion(
            "That looks like a database command. This assistant is read-only and only "
            "answers plain-English questions about sales.")

    hit = UNSUPPORTED_RE.search(q)
    if hit:
        raise UnsupportedQuestion(f"Questions involving '{hit.group(1)}' are not supported yet.")

    for name in _known_entities():
        if re.search(rf"\b{re.escape(name)}\b", q):
            raise UnsupportedQuestion(
                f"Filtering by a specific region or product ('{name}') is not supported yet.")

    months = _find_months(q)

    if CHANGE_RE.search(q):
        if len(months) != 2:
            raise UnsupportedQuestion(
                "To compare revenue, name exactly two months, e.g. "
                "'How did revenue change between February and March?'")
        return {"intent": "revenue_change",
                "params": {"month_a": months[0], "month_b": months[1]},
                "interpreter": "rules"}

    if months:
        raise UnsupportedQuestion(
            "Questions about a single month are not supported yet. "
            "Ask for the monthly trend, or compare two months.")

    if TREND_RE.search(q):
        return {"intent": "monthly_trend", "params": {}, "interpreter": "rules"}

    if REGION_RE.search(q) and MEASURE_RE.search(q):
        return {"intent": "top_region", "params": {}, "interpreter": "rules"}

    if PRODUCT_RE.search(q) and MEASURE_RE.search(q):
        return {"intent": "top_product", "params": {}, "interpreter": "rules"}

    if REVENUE_RE.search(q) and (TOTAL_RE.search(q) or not GROUPING_RE.search(q)):
        return {"intent": "total_revenue", "params": {}, "interpreter": "rules"}

    raise UnsupportedQuestion("I can only answer questions about revenue by product, region, or month.")
