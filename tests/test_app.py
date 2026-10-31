import pytest
from fastapi.testclient import TestClient

from app.ai import LLMOutputError, LLMUnavailable, interpret_with_ai, validate_llm_output
from app.analytics import AnalyticsError, run_intent
from app.database import load_csv, validate_row
from app.interpreter import UnsupportedQuestion
from app.main import app

GOOD_ROW = {
    "Transaction_Id": "TXN9001", "Order_date": "05-01-2026", "Product": "Desk",
    "Category": "Furniture", "Region": "North", "Sales_channel": "Online",
    "Quantity": "2", "Unit_price": "100", "Discount_amount": "10", "Status": "Completed",
}


@pytest.fixture(scope="session", autouse=True)
def database():
    load_csv()


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    # Tests must never call the real LLM, even if a .env key exists.
    monkeypatch.setenv("GEMINI_API_KEY", "")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def ask(client, question):
    return client.post("/ask", json={"question": question})


# --- data cleaning ---
def test_valid_row_is_cleaned_and_date_parsed_day_first():
    clean, errors = validate_row(GOOD_ROW)
    assert errors is None
    assert clean["order_date"] == "2026-01-05"  # 5 January, not 1 May
    assert clean["order_month"] == "2026-01"


def test_zero_quantity_is_rejected():
    _, errors = validate_row({**GOOD_ROW, "Quantity": "0"})
    assert "quantity must be > 0" in errors


def test_missing_unit_price_is_rejected():
    _, errors = validate_row({**GOOD_ROW, "Unit_price": ""})
    assert "missing Unit_price" in errors


def test_loader_summary_counts():
    summary = load_csv()
    assert summary == {"total_rows": 51, "loaded": 49, "rejected": 2}


# --- analytics ---
def test_total_revenue_excludes_returned_orders():
    result = run_intent("total_revenue")
    assert result["data"][0]["total_revenue"] == 1439200.0


def test_top_product_is_monitor():
    assert run_intent("top_product")["data"][0]["product"] == "Monitor"


def test_revenue_change_feb_to_mar():
    result = run_intent("revenue_change", {"month_a": "2026-02", "month_b": "2026-03"})
    assert result["data"][2]["revenue"] == -10700.0


def test_unknown_month_raises():
    with pytest.raises(AnalyticsError):
        run_intent("revenue_change", {"month_a": "2026-02", "month_b": "2026-09"})


def test_intent_outside_allowlist_raises():
    with pytest.raises(AnalyticsError):
        run_intent("drop_table")


# --- AI layer ---
def test_llm_hallucinated_month_is_rejected():
    data = {"intent": "revenue_change", "params": {"month_a": "2026-02", "month_b": "2026-09"}}
    with pytest.raises(LLMOutputError):
        validate_llm_output(data, "how did revenue change between feb and mar")


def test_llm_intent_outside_allowlist_is_rejected():
    with pytest.raises(LLMOutputError):
        validate_llm_output({"intent": "drop_table", "params": {}}, "anything")


def test_llm_failure_falls_back_to_rules():
    def broken_llm(system, text):
        raise LLMUnavailable("simulated outage")

    result = interpret_with_ai("What is the total revenue?", call_llm=broken_llm)
    assert result["interpreter"] == "rules"
    assert result["fallback_reason"] == "simulated outage"


def test_precheck_blocks_sql_before_llm():
    with pytest.raises(UnsupportedQuestion):
        interpret_with_ai("DROP TABLE sales;", call_llm=lambda s, t: "{}")


# --- API ---
def test_api_valid_question(client):
    r = ask(client, "Which product generated the highest revenue?")
    assert r.status_code == 200
    assert r.json()["intent"] == "top_product"


def test_api_unsupported_question_returns_400(client):
    r = ask(client, "Which region had the lowest sales?")
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_question"


def test_api_blank_question_returns_422(client):
    assert ask(client, "   ").status_code == 422


def test_api_sql_injection_attempt_is_refused(client):
    r = ask(client, "DROP TABLE sales;")
    assert r.status_code == 400
