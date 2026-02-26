"""
Generate the Global Retail Sales dataset (10,000 transactions) and load it into DuckDB.
Run from the backend/ directory:
    python data/generate_dataset.py [--db-path data/olap.duckdb] [--rows 10000] [--seed 42]
"""

import random
import sys
import os
import argparse
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Domain data
# ---------------------------------------------------------------------------

REGIONS_COUNTRIES = {
    "North America": ["United States", "Canada", "Mexico"],
    "Europe":        ["United Kingdom", "Germany", "France", "Spain", "Italy"],
    "Asia Pacific":  ["Japan", "China", "Australia", "India", "South Korea"],
    "Latin America": ["Brazil", "Argentina", "Colombia", "Chile"],
}

CATEGORIES_SUBCATEGORIES = {
    "Electronics":     ["Phones", "Laptops", "Tablets", "Accessories", "Audio"],
    "Furniture":       ["Chairs", "Tables", "Desks", "Cabinets", "Shelving"],
    "Office Supplies": ["Paper", "Pens & Pencils", "Binders", "Printers", "Organizers"],
    "Clothing":        ["Shirts", "Pants", "Shoes", "Jackets", "Accessories"],
}

CUSTOMER_SEGMENTS = ["Consumer", "Corporate", "Home Office", "Small Business"]

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Susan", "Richard", "Jessica", "Joseph", "Sarah",
    "Thomas", "Karen", "Charles", "Lisa", "Emma", "Oliver", "Sophia", "Liam",
    "Ava", "Noah", "Isabella", "Mason", "Mia", "Ethan",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson",
    "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin",
    "Thompson", "Garcia", "Martinez", "Robinson", "Clark", "Rodriguez", "Lewis",
    "Lee", "Walker", "Hall", "Allen", "Young", "Hernandez", "King",
]

# Price ranges per category (min, max unit price in USD)
PRICE_RANGES = {
    "Electronics":     (49.99,  1999.99),
    "Furniture":       (29.99,   899.99),
    "Office Supplies": ( 2.99,   199.99),
    "Clothing":        ( 9.99,   299.99),
}

# Margin ranges per category (cost as fraction of price)
COST_FRACTIONS = {
    "Electronics":     (0.55, 0.75),
    "Furniture":       (0.45, 0.65),
    "Office Supplies": (0.35, 0.55),
    "Clothing":        (0.30, 0.50),
}

# Seasonal demand multiplier by month (index 0 = Jan)
SEASONAL_WEIGHTS = [
    0.80, 0.72, 0.88, 0.90, 0.95, 0.92,   # Jan-Jun
    0.88, 0.85, 0.95, 1.05, 1.35, 1.50,   # Jul-Dec (peak Nov-Dec)
]


def build_dim_date(start: date, end: date) -> list[dict]:
    rows = []
    current = start
    while current <= end:
        q = (current.month - 1) // 3 + 1
        rows.append({
            "date_key":    int(current.strftime("%Y%m%d")),
            "full_date":   current.isoformat(),
            "year":        current.year,
            "quarter":     q,
            "quarter_name": f"Q{q}",
            "month":       current.month,
            "month_name":  current.strftime("%B"),
            "week":        current.isocalendar()[1],
            "day":         current.day,
        })
        current += timedelta(days=1)
    return rows


def build_dim_geography() -> list[dict]:
    rows = []
    key = 1
    for region, countries in REGIONS_COUNTRIES.items():
        for country in countries:
            rows.append({"geo_key": key, "region": region, "country": country})
            key += 1
    return rows


def build_dim_product() -> list[dict]:
    rows = []
    key = 1
    for category, subcats in CATEGORIES_SUBCATEGORIES.items():
        for subcat in subcats:
            for variant_n in range(1, 4):  # 3 products per subcategory
                name = f"{subcat} Model {variant_n}"
                rows.append({
                    "product_key":  key,
                    "product_name": name,
                    "category":     category,
                    "subcategory":  subcat,
                })
                key += 1
    return rows


def build_dim_customer(n: int = 200) -> list[dict]:
    rows = []
    rng = random.Random(99)
    for i in range(1, n + 1):
        fname = rng.choice(FIRST_NAMES)
        lname = rng.choice(LAST_NAMES)
        rows.append({
            "customer_key":     i,
            "customer_name":    f"{fname} {lname}",
            "customer_segment": rng.choice(CUSTOMER_SEGMENTS),
        })
    return rows


def build_fact_sales(
    n: int,
    date_rows: list[dict],
    geo_rows: list[dict],
    product_rows: list[dict],
    customer_rows: list[dict],
    rng: random.Random,
) -> list[dict]:
    # Build lookup for seasonal weights by date_key
    date_key_to_month = {r["date_key"]: r["month"] for r in date_rows}
    date_keys = [r["date_key"] for r in date_rows]
    geo_keys = [r["geo_key"] for r in geo_rows]
    product_map = {r["product_key"]: r for r in product_rows}
    product_keys = list(product_map.keys())
    customer_keys = [r["customer_key"] for r in customer_rows]

    rows = []
    for i in range(1, n + 1):
        # Weighted date selection by seasonal demand
        month_weights = [SEASONAL_WEIGHTS[date_key_to_month[dk] - 1] for dk in date_keys]
        date_key = rng.choices(date_keys, weights=month_weights, k=1)[0]
        geo_key = rng.choice(geo_keys)
        product_key = rng.choice(product_keys)
        customer_key = rng.choice(customer_keys)

        prod = product_map[product_key]
        category = prod["category"]
        pmin, pmax = PRICE_RANGES[category]
        cmin, cmax = COST_FRACTIONS[category]

        unit_price = round(rng.uniform(pmin, pmax), 2)
        cost_frac = rng.uniform(cmin, cmax)
        unit_cost = round(unit_price * cost_frac, 2)
        quantity = rng.randint(1, 10)

        revenue = round(unit_price * quantity, 2)
        cost = round(unit_cost * quantity, 2)
        profit = round(revenue - cost, 2)
        margin = round(profit / revenue, 4) if revenue > 0 else 0.0

        rows.append({
            "sale_id":       i,
            "date_key":      date_key,
            "geo_key":       geo_key,
            "product_key":   product_key,
            "customer_key":  customer_key,
            "quantity":      quantity,
            "unit_price":    unit_price,
            "unit_cost":     unit_cost,
            "revenue":       revenue,
            "cost":          cost,
            "profit":        profit,
            "profit_margin": margin,
        })
    return rows


def insert_rows(conn, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" * len(cols))
    col_list = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"
    data = [tuple(r[c] for c in cols) for r in rows]
    conn.executemany(sql, data)


def main():
    parser = argparse.ArgumentParser(description="Generate OLAP dataset into DuckDB")
    parser.add_argument("--db-path", default="data/olap.duckdb", help="DuckDB file path")
    parser.add_argument("--rows", type=int, default=10000, help="Number of fact rows")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not installed. Run: pip install duckdb", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to DuckDB at: {db_path}")
    conn = duckdb.connect(str(db_path))

    schema_path = Path(__file__).parent / "schema.sql"
    print(f"Applying schema from: {schema_path}")
    conn.execute(schema_path.read_text())

    rng = random.Random(args.seed)

    print("Building dimension tables...")
    start_date = date(2022, 1, 1)
    end_date = date(2024, 12, 31)
    date_rows = build_dim_date(start_date, end_date)
    geo_rows = build_dim_geography()
    product_rows = build_dim_product()
    customer_rows = build_dim_customer(200)

    print(f"  dim_date:     {len(date_rows):,} rows ({start_date} → {end_date})")
    print(f"  dim_geography:{len(geo_rows):,} rows")
    print(f"  dim_product:  {len(product_rows):,} rows")
    print(f"  dim_customer: {len(customer_rows):,} rows")

    print(f"Building fact_sales: {args.rows:,} rows...")
    fact_rows = build_fact_sales(args.rows, date_rows, geo_rows, product_rows, customer_rows, rng)

    print("Inserting into DuckDB...")
    conn.begin()
    insert_rows(conn, "dim_date", date_rows)
    insert_rows(conn, "dim_geography", geo_rows)
    insert_rows(conn, "dim_product", product_rows)
    insert_rows(conn, "dim_customer", customer_rows)
    insert_rows(conn, "fact_sales", fact_rows)
    conn.commit()

    # Verify
    counts = {}
    for table in ["dim_date", "dim_geography", "dim_product", "dim_customer", "fact_sales"]:
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    conn.close()

    print("\nDataset generation complete:")
    for table, count in counts.items():
        print(f"  {table:<20}: {count:>8,} rows")
    print(f"\nDuckDB file: {db_path.resolve()}")


if __name__ == "__main__":
    main()
