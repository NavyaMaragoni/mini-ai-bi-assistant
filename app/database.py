"""Data layer: reads the CSV, cleans/validates each row, and loads it into SQLite.

Valid rows  -> table `sales`
Invalid rows -> table `rejected_records` (with the reason), so nothing is silently lost.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "sales.db"
CSV_PATH = BASE_DIR / "data" / "sales.csv"

SCHEMA = """
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS rejected_records;

CREATE TABLE sales (
    transaction_id  TEXT PRIMARY KEY,
    order_date      TEXT NOT NULL,              -- ISO format YYYY-MM-DD
    order_month     TEXT NOT NULL,              -- YYYY-MM, for monthly grouping
    product         TEXT NOT NULL,
    category        TEXT NOT NULL,
    region          TEXT NOT NULL,
    sales_channel   TEXT NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL    NOT NULL CHECK (unit_price > 0),
    discount_amount REAL    NOT NULL CHECK (discount_amount >= 0),
    status          TEXT NOT NULL
);

CREATE TABLE rejected_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT,
    reason         TEXT NOT NULL,
    raw_row        TEXT NOT NULL                -- the original row as JSON
);
"""

TEXT_FIELDS = ["Product", "Category", "Region", "Sales_channel", "Status"]


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def validate_row(row):
    """Return (clean_dict, None) if the row is valid, else (None, [reasons])."""
    errors = []

    txn_id = row.get("Transaction_Id", "").strip()
    if not txn_id:
        errors.append("missing Transaction_Id")

    # Dates are DD-MM-YYYY in the source file
    order_date = None
    try:
        order_date = datetime.strptime(row.get("Order_date", "").strip(), "%d-%m-%Y").date()
    except ValueError:
        errors.append("invalid Order_date (expected DD-MM-YYYY)")

    text = {}
    for field in TEXT_FIELDS:
        value = row.get(field, "").strip()
        if not value:
            errors.append(f"missing {field}")
        text[field] = value

    quantity = None
    try:
        quantity = int(row.get("Quantity", "").strip())
        if quantity <= 0:
            errors.append("quantity must be > 0")
    except ValueError:
        errors.append("missing or non-numeric Quantity")

    unit_price = None
    raw_price = row.get("Unit_price", "").strip()
    if not raw_price:
        errors.append("missing Unit_price")
    else:
        try:
            unit_price = float(raw_price)
            if unit_price <= 0:
                errors.append("Unit_price must be > 0")
        except ValueError:
            errors.append("non-numeric Unit_price")

    # A blank discount is treated as 0 (no discount)
    discount = 0.0
    raw_discount = row.get("Discount_amount", "").strip()
    if raw_discount:
        try:
            discount = float(raw_discount)
            if discount < 0:
                errors.append("Discount_amount must be >= 0")
        except ValueError:
            errors.append("non-numeric Discount_amount")

    if quantity and quantity > 0 and unit_price and discount > quantity * unit_price:
        errors.append("Discount_amount is larger than the gross amount")

    if errors:
        return None, errors

    return {
        "transaction_id": txn_id,
        "order_date": order_date.isoformat(),
        "order_month": order_date.strftime("%Y-%m"),
        "product": text["Product"],
        "category": text["Category"],
        "region": text["Region"],
        "sales_channel": text["Sales_channel"],
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_amount": discount,
        "status": text["Status"],
    }, None


def load_csv(csv_path=CSV_PATH, db_path=DB_PATH):
    """(Re)build the database from the CSV. Returns a summary dict."""
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    conn = get_connection(db_path)
    conn.executescript(SCHEMA)

    seen_ids = set()
    loaded, rejected = 0, 0

    for row in df.to_dict(orient="records"):
        clean, errors = validate_row(row)

        if clean and clean["transaction_id"] in seen_ids:
            clean, errors = None, ["duplicate Transaction_Id"]

        if errors:
            conn.execute(
                "INSERT INTO rejected_records (transaction_id, reason, raw_row) VALUES (?, ?, ?)",
                (row.get("Transaction_Id", ""), "; ".join(errors), json.dumps(row)),
            )
            rejected += 1
            continue

        seen_ids.add(clean["transaction_id"])
        conn.execute(
            """INSERT INTO sales VALUES
               (:transaction_id, :order_date, :order_month, :product, :category,
                :region, :sales_channel, :quantity, :unit_price, :discount_amount, :status)""",
            clean,
        )
        loaded += 1

    conn.commit()
    conn.close()
    return {"total_rows": len(df), "loaded": loaded, "rejected": rejected}


if __name__ == "__main__":
    summary = load_csv()
    print("Load summary:", summary)
