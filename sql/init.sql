-- ============================================================
-- CRM Database Schema (Star Schema)
-- ============================================================

CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id   VARCHAR(20) PRIMARY KEY,
    customer_name VARCHAR(100),
    segment       VARCHAR(50),
    city          VARCHAR(100),
    state         VARCHAR(100),
    region        VARCHAR(50),
    country       VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_id   VARCHAR(20) PRIMARY KEY,
    product_name VARCHAR(200),
    category     VARCHAR(50),
    sub_category VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     DATE PRIMARY KEY,
    year         INT,
    quarter      INT,
    month        INT,
    month_name   VARCHAR(20),
    week         INT,
    day_of_week  VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id    VARCHAR(20),
    order_date  DATE,
    ship_date   DATE,
    ship_mode   VARCHAR(50),
    customer_id VARCHAR(20) REFERENCES dim_customers(customer_id),
    product_id  VARCHAR(20) REFERENCES dim_products(product_id),
    sales       NUMERIC(12,2),
    quantity    INT,
    discount    NUMERIC(5,2),
    profit      NUMERIC(12,2),
    PRIMARY KEY (order_id, product_id)
);

-- Bảng log chất lượng dữ liệu
CREATE TABLE IF NOT EXISTS data_quality_log (
    id           SERIAL PRIMARY KEY,
    run_date     TIMESTAMP DEFAULT NOW(),
    check_name   VARCHAR(100),
    status       VARCHAR(10),   -- PASS / FAIL
    rows_checked INT,
    rows_failed  INT,
    message      TEXT
);

-- Index
CREATE INDEX IF NOT EXISTS idx_orders_date    ON fact_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_cust    ON fact_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_product ON fact_orders(product_id);

-- ── VIEWS ────────────────────────────────────────────────────

CREATE OR REPLACE VIEW vw_monthly_kpi AS
SELECT
    DATE_TRUNC('month', order_date)::DATE          AS month,
    COUNT(DISTINCT order_id)                        AS total_orders,
    COUNT(DISTINCT customer_id)                     AS unique_customers,
    ROUND(SUM(sales)::NUMERIC, 2)                   AS total_revenue,
    ROUND(SUM(profit)::NUMERIC, 2)                  AS total_profit,
    ROUND(AVG(discount)::NUMERIC * 100, 2)          AS avg_discount_pct,
    ROUND((SUM(profit)/NULLIF(SUM(sales),0)*100)::NUMERIC, 2) AS profit_margin_pct
FROM fact_orders
GROUP BY 1 ORDER BY 1;

CREATE OR REPLACE VIEW vw_revenue_by_region_category AS
SELECT
    c.region,
    p.category,
    ROUND(SUM(o.sales)::NUMERIC,  2) AS revenue,
    ROUND(SUM(o.profit)::NUMERIC, 2) AS profit,
    COUNT(DISTINCT o.order_id)       AS orders
FROM fact_orders o
JOIN dim_customers c ON o.customer_id = c.customer_id
JOIN dim_products  p ON o.product_id  = p.product_id
GROUP BY c.region, p.category
ORDER BY revenue DESC;

CREATE OR REPLACE VIEW vw_top_customers AS
SELECT
    c.customer_id,
    c.customer_name,
    c.segment,
    c.region,
    ROUND(SUM(o.sales)::NUMERIC,  2) AS total_revenue,
    ROUND(SUM(o.profit)::NUMERIC, 2) AS total_profit,
    COUNT(DISTINCT o.order_id)       AS order_count,
    ROUND(AVG(o.sales)::NUMERIC,  2) AS avg_order_value
FROM fact_orders o
JOIN dim_customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name, c.segment, c.region
ORDER BY total_revenue DESC
LIMIT 10;

CREATE OR REPLACE VIEW vw_anomaly_orders AS
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    p.product_name,
    o.sales,
    o.discount,
    o.profit,
    ROUND((o.profit/NULLIF(o.sales,0)*100)::NUMERIC, 2) AS margin_pct
FROM fact_orders o
JOIN dim_customers c ON o.customer_id = c.customer_id
JOIN dim_products  p ON o.product_id  = p.product_id
WHERE o.profit < -50 OR o.discount > 0.4
ORDER BY o.profit ASC;
