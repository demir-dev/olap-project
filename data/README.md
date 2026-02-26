# Dataset: Global Retail Sales

## Overview

| Attribute   | Value                                           |
|-------------|--------------------------------------------------|
| Records     | 10,000 transactions                              |
| Time Period  | January 2022 – December 2024                     |
| Regions     | North America, Europe, Asia Pacific, Latin America |
| Categories  | Electronics, Furniture, Office Supplies, Clothing |

## Generating the Dataset

The dataset is auto-generated when the backend starts (if the database is empty).
To regenerate manually:

```bash
# From the backend/ directory:
python data/generate_dataset.py

# With custom options:
python data/generate_dataset.py --rows 10000 --seed 42 --db-path data/olap.duckdb
```

## Schema

The flat CSV is loaded into a **star schema** in DuckDB:

```
         dim_date
              |
dim_geography --- fact_sales --- dim_product
              |
         dim_customer
```

### Dimensions & Measures

**Dimensions:**
- `order_date`, `year`, `quarter`, `quarter_name`, `month`, `month_name` (time)
- `region`, `country` (geography)
- `category`, `subcategory`, `product_name` (product)
- `customer_segment`, `customer_name` (customer)

**Measures:**
- `quantity` — units sold
- `unit_price` — sale price per unit
- `unit_cost` — cost per unit
- `revenue` — quantity × unit_price
- `cost` — quantity × unit_cost
- `profit` — revenue − cost
- `profit_margin` — profit / revenue (0.0–1.0)

### Hierarchies

| Hierarchy  | Levels                         |
|------------|--------------------------------|
| Time       | Year → Quarter → Month         |
| Geography  | Region → Country               |
| Product    | Category → Subcategory         |

## Sample Data

| Region        | Category    | Revenue   | Profit   | Margin |
|---------------|-------------|-----------|----------|--------|
| North America | Electronics | $1,234,567| $321,456 | 26.0%  |
| Europe        | Furniture   | $876,543  | $198,765 | 22.7%  |
| Asia Pacific  | Clothing    | $654,321  | $167,890 | 25.7%  |
| Latin America | Office Sup. | $345,678  | $98,765  | 28.6%  |
