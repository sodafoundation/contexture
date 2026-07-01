-- ============================================================================
-- ClickHouse E-Commerce OCS Schema
-- Application: E-commerce
-- Run: docker exec -i contexture-clickhouse clickhouse-client < scripts/clickhouse/ecommerce_ocs_schema.sql
-- ============================================================================

-- ── Database ─────────────────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS ecommerce;

-- ── 1. customers ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.customers
(
    customer_id  UInt32,
    name         String,
    email        String,
    city         String
)
ENGINE = MergeTree()
ORDER BY customer_id;

-- ── 2. products ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.products
(
    product_id   UInt32,
    name         String,
    category     String,
    price        Float64,
    stock        UInt32
)
ENGINE = MergeTree()
ORDER BY product_id;

-- ── 3. orders ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.orders
(
    order_id     UInt32,
    customer_id  UInt32,
    product_id   UInt32,
    quantity     UInt32,
    order_date   Date
)
ENGINE = MergeTree()
ORDER BY (order_id, customer_id);

-- ── Truncate existing data (idempotent re-runs) ─────────────────────────────
TRUNCATE TABLE ecommerce.customers;
TRUNCATE TABLE ecommerce.products;
TRUNCATE TABLE ecommerce.orders;

-- ── Insert sample data ──────────────────────────────────────────────────────

-- Customers
INSERT INTO ecommerce.customers (customer_id, name, email, city) VALUES
    (1, 'Rahul',   'rahul@example.com',   'Mumbai'),
    (2, 'Priya',   'priya@example.com',   'Delhi'),
    (3, 'Amit',    'amit@example.com',    'Bangalore'),
    (4, 'Sneha',   'sneha@example.com',   'Chennai'),
    (5, 'Vikram',  'vikram@example.com',  'Hyderabad');

-- Products
INSERT INTO ecommerce.products (product_id, name, category, price, stock) VALUES
    (101, 'Laptop',     'Electronics', 75000.00,  50),
    (102, 'Mouse',      'Electronics',  1500.00, 200),
    (103, 'Keyboard',   'Electronics',  3000.00, 150),
    (104, 'Headphones', 'Electronics',  5000.00, 100),
    (105, 'Notebook',   'Stationery',    200.00, 500);

-- Orders (Rahul bought Laptop and Mouse, matching the MongoDB sample query)
INSERT INTO ecommerce.orders (order_id, customer_id, product_id, quantity, order_date) VALUES
    (1001, 1, 101, 1, '2026-06-15'),
    (1002, 1, 102, 2, '2026-06-16'),
    (1003, 2, 103, 1, '2026-06-16'),
    (1004, 2, 104, 1, '2026-06-17'),
    (1005, 3, 105, 5, '2026-06-17'),
    (1006, 4, 101, 1, '2026-06-18'),
    (1007, 5, 102, 3, '2026-06-18');

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Show all tables
SELECT '── TABLES IN ecommerce ──' AS section;
SHOW TABLES FROM ecommerce;

-- Show schema of each table
SELECT '── SCHEMA: customers ──' AS section;
DESCRIBE ecommerce.customers;

SELECT '── SCHEMA: products ──' AS section;
DESCRIBE ecommerce.products;

SELECT '── SCHEMA: orders ──' AS section;
DESCRIBE ecommerce.orders;

-- Verify row counts
SELECT '── ROW COUNTS ──' AS section;
SELECT 'customers' AS table_name, count() AS rows FROM ecommerce.customers
UNION ALL
SELECT 'products',  count() FROM ecommerce.products
UNION ALL
SELECT 'orders',    count() FROM ecommerce.orders;

-- Verify relationships: "What products did Rahul buy?"
SELECT '── SAMPLE QUERY: What products did Rahul buy? ──' AS section;
SELECT
    c.name       AS customer_name,
    p.name       AS product_name,
    o.quantity   AS quantity,
    o.order_date AS order_date
FROM ecommerce.orders AS o
INNER JOIN ecommerce.customers AS c ON o.customer_id = c.customer_id
INNER JOIN ecommerce.products  AS p ON o.product_id  = p.product_id
WHERE c.name = 'Rahul';

-- Full relationship verification: all customers with their orders
SELECT '── ALL CUSTOMER-PRODUCT RELATIONSHIPS ──' AS section;
SELECT
    c.name       AS customer,
    p.name       AS product,
    p.category   AS category,
    o.quantity   AS qty,
    p.price      AS unit_price,
    (o.quantity * p.price) AS total_amount
FROM ecommerce.orders AS o
INNER JOIN ecommerce.customers AS c ON o.customer_id = c.customer_id
INNER JOIN ecommerce.products  AS p ON o.product_id  = p.product_id
ORDER BY c.name, o.order_date;
