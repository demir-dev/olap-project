-- OLAP Star Schema DDL for DuckDB
-- Global Retail Sales Data Model

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,   -- Surrogate key: YYYYMMDD
    full_date    DATE NOT NULL,
    year         SMALLINT NOT NULL,
    quarter      TINYINT NOT NULL,      -- 1, 2, 3, 4
    quarter_name VARCHAR(2) NOT NULL,   -- Q1, Q2, Q3, Q4
    month        TINYINT NOT NULL,      -- 1-12
    month_name   VARCHAR(9) NOT NULL,   -- January..December
    week         TINYINT NOT NULL,      -- ISO week 1-53
    day          TINYINT NOT NULL       -- Day of month 1-31
);

CREATE TABLE IF NOT EXISTS dim_geography (
    geo_key  INTEGER PRIMARY KEY,
    region   VARCHAR(50) NOT NULL,      -- North America, Europe, Asia Pacific, Latin America
    country  VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key  INTEGER PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    category     VARCHAR(50) NOT NULL,  -- Electronics, Furniture, Office Supplies, Clothing
    subcategory  VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key     INTEGER PRIMARY KEY,
    customer_name    VARCHAR(200) NOT NULL,
    customer_segment VARCHAR(50) NOT NULL  -- Consumer, Corporate, Home Office, Small Business
);

-- ============================================================
-- FACT TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS fact_sales (
    sale_id       INTEGER PRIMARY KEY,
    date_key      INTEGER NOT NULL REFERENCES dim_date(date_key),
    geo_key       INTEGER NOT NULL REFERENCES dim_geography(geo_key),
    product_key   INTEGER NOT NULL REFERENCES dim_product(product_key),
    customer_key  INTEGER NOT NULL REFERENCES dim_customer(customer_key),
    quantity      INTEGER NOT NULL,
    unit_price    DECIMAL(10,2) NOT NULL,
    unit_cost     DECIMAL(10,2) NOT NULL,
    revenue       DECIMAL(12,2) NOT NULL,   -- quantity * unit_price
    cost          DECIMAL(12,2) NOT NULL,   -- quantity * unit_cost
    profit        DECIMAL(12,2) NOT NULL,   -- revenue - cost
    profit_margin DECIMAL(5,4) NOT NULL     -- profit / revenue (0.0 - 1.0)
);

-- ============================================================
-- PERFORMANCE INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_fs_date     ON fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fs_geo      ON fact_sales(geo_key);
CREATE INDEX IF NOT EXISTS idx_fs_product  ON fact_sales(product_key);
CREATE INDEX IF NOT EXISTS idx_fs_customer ON fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS idx_dd_year     ON dim_date(year);
CREATE INDEX IF NOT EXISTS idx_dd_quarter  ON dim_date(quarter);
CREATE INDEX IF NOT EXISTS idx_dd_month    ON dim_date(month);
CREATE INDEX IF NOT EXISTS idx_dg_region   ON dim_geography(region);
CREATE INDEX IF NOT EXISTS idx_dp_category ON dim_product(category);
