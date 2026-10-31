import pandas as pd

# Read everything as text first, so we see the raw data exactly as it is
df = pd.read_csv("data/sales.csv", dtype=str, keep_default_na=False)

print("Shape (rows, cols):", df.shape)
print()

print("Blank values per column (only showing columns with blanks):")
blanks = (df.apply(lambda col: col.str.strip() == "")).sum()
print(blanks[blanks > 0])
print()

print("Duplicate Transaction_Ids:", df.Transaction_Id.duplicated().sum())
print()

# Dates are DD-MM-YYYY, so we must say so explicitly
dates = pd.to_datetime(df.Order_date, format="%d-%m-%Y", errors="coerce")
print("Invalid dates:", dates.isna().sum())
print("Date range:", dates.min().date(), "to", dates.max().date())
print()

qty = pd.to_numeric(df.Quantity, errors="coerce")
price = pd.to_numeric(df.Unit_price, errors="coerce")
disc = pd.to_numeric(df.Discount_amount, errors="coerce")
print("Quantity <= 0 or invalid:", df[~(qty > 0)].Transaction_Id.tolist())
print("Unit_price missing/invalid:", df[price.isna()].Transaction_Id.tolist())
print("Discount larger than gross:", df[disc > qty * price].Transaction_Id.tolist())
print()

print("Status counts:", df.Status.value_counts().to_dict())
print("Non-completed rows:", df[df.Status != "Completed"].Transaction_Id.tolist())
print("Regions:", sorted(df.Region.unique()))
print("Categories:", sorted(df.Category.unique()))
