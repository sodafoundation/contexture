-- ============================================================================
-- ClickHouse Schema Init for SODA Contexture
-- Matches the performance report schema: service_dependencies + metrics tables
-- Run: docker exec -i contexture-clickhouse clickhouse-client < scripts/clickhouse/init.sql
-- ============================================================================

-- ── 1. service_dependencies ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS default.service_dependencies
(
    source_service   String,
    target_service   String,
    call_type        String,
    avg_latency_ms   Float64,
    error_rate       Float64,
    requests_per_min Float64,
    recorded_at      DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (source_service, target_service, recorded_at)
COMMENT 'Service dependency topology data for OCS context building';

-- ── 2. metrics ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS default.metrics
(
    service_name String,
    metric_name  String,
    metric_value Float64,
    labels       String,
    recorded_at  DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (service_name, metric_name, recorded_at)
COMMENT 'Time-series metrics data from Prometheus and other sources';

-- ── 3. clusters ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS default.clusters
(
    cluster_id   String,
    cluster_name String,
    region       String,
    cpu_usage    Float64,
    memory_usage Float64,
    node_count   UInt32,
    recorded_at  DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (cluster_id, recorded_at)
COMMENT 'Cluster performance and resource metrics';

-- ── Sample data: service_dependencies ────────────────────────────────────────
INSERT INTO default.service_dependencies (source_service, target_service, call_type, avg_latency_ms, error_rate, requests_per_min, recorded_at) VALUES ('frontend', 'api-gateway', 'HTTP', 12.5, 0.001, 450.0, now() - INTERVAL 1 HOUR), ('api-gateway', 'user-service', 'gRPC', 8.3, 0.000, 380.0, now() - INTERVAL 1 HOUR), ('api-gateway', 'product-service', 'gRPC', 15.2, 0.002, 290.0, now() - INTERVAL 2 HOUR), ('api-gateway', 'order-service', 'gRPC', 22.7, 0.003, 150.0, now() - INTERVAL 2 HOUR), ('order-service', 'payment-service', 'HTTP', 45.0, 0.010, 120.0, now() - INTERVAL 3 HOUR), ('order-service', 'inventory-svc', 'HTTP', 18.3, 0.001, 140.0, now() - INTERVAL 3 HOUR), ('payment-service', 'fraud-detector', 'HTTP', 95.0, 0.005, 60.0, now() - INTERVAL 4 HOUR), ('frontend', 'api-gateway', 'HTTP', 13.1, 0.002, 480.0, now() - INTERVAL 5 HOUR), ('api-gateway', 'user-service', 'gRPC', 9.0, 0.001, 400.0, now() - INTERVAL 5 HOUR), ('api-gateway', 'product-service', 'gRPC', 14.8, 0.001, 310.0, now() - INTERVAL 6 HOUR);

-- ── Sample data: metrics ─────────────────────────────────────────────────────
INSERT INTO default.metrics (service_name, metric_name, metric_value, labels, recorded_at) VALUES ('frontend', 'cpu_usage_percent', 35.2, '{"env":"prod","pod":"frontend-abc"}', now() - INTERVAL 30 MINUTE), ('frontend', 'memory_usage_mb', 512.0, '{"env":"prod","pod":"frontend-abc"}', now() - INTERVAL 30 MINUTE), ('api-gateway', 'cpu_usage_percent', 55.7, '{"env":"prod","pod":"api-gw-xyz"}', now() - INTERVAL 30 MINUTE), ('api-gateway', 'memory_usage_mb', 1024.0, '{"env":"prod","pod":"api-gw-xyz"}', now() - INTERVAL 30 MINUTE), ('user-service', 'cpu_usage_percent', 22.1, '{"env":"prod","pod":"user-svc-111"}', now() - INTERVAL 30 MINUTE), ('product-service', 'cpu_usage_percent', 31.8, '{"env":"prod","pod":"product-svc-222"}', now() - INTERVAL 30 MINUTE), ('order-service', 'cpu_usage_percent', 48.4, '{"env":"prod","pod":"order-svc-333"}', now() - INTERVAL 30 MINUTE), ('payment-service', 'cpu_usage_percent', 72.6, '{"env":"prod","pod":"payment-svc-444"}', now() - INTERVAL 30 MINUTE), ('payment-service', 'error_rate', 0.01, '{"env":"prod"}', now() - INTERVAL 30 MINUTE), ('fraud-detector', 'cpu_usage_percent', 88.3, '{"env":"prod","pod":"fraud-svc-555"}', now() - INTERVAL 30 MINUTE);

-- ── Sample data: clusters ─────────────────────────────────────────────────────
INSERT INTO default.clusters (cluster_id, cluster_name, region, cpu_usage, memory_usage, node_count, recorded_at) VALUES ('cluster-01', 'prod-us-east', 'us-east-1', 45.3, 62.1, 10, now() - INTERVAL 1 DAY), ('cluster-02', 'prod-eu-west', 'eu-west-1', 38.7, 55.3, 8, now() - INTERVAL 1 DAY), ('cluster-03', 'prod-ap-south', 'ap-south-1', 72.9, 81.5, 12, now() - INTERVAL 1 DAY), ('cluster-04', 'staging-us', 'us-west-2', 21.5, 40.2, 4, now() - INTERVAL 1 DAY), ('cluster-01', 'prod-us-east', 'us-east-1', 50.1, 65.4, 10, now() - INTERVAL 12 HOUR), ('cluster-02', 'prod-eu-west', 'eu-west-1', 42.3, 58.7, 8, now() - INTERVAL 12 HOUR), ('cluster-03', 'prod-ap-south', 'ap-south-1', 68.2, 79.3, 12, now() - INTERVAL 12 HOUR), ('cluster-04', 'staging-us', 'us-west-2', 19.8, 38.6, 4, now() - INTERVAL 12 HOUR), ('cluster-01', 'prod-us-east', 'us-east-1', 47.8, 63.2, 10, now()), ('cluster-02', 'prod-eu-west', 'eu-west-1', 40.5, 57.0, 8, now()), ('cluster-03', 'prod-ap-south', 'ap-south-1', 71.4, 80.0, 12, now()), ('cluster-04', 'staging-us', 'us-west-2', 20.3, 39.1, 4, now());

-- ============================================================================
-- E-commerce Schema
-- ============================================================================

CREATE DATABASE IF NOT EXISTS ecommerce;

-- ── 1. customers ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.customers
(
    customer_id UInt32,
    name String,
    email String,
    city String
)
ENGINE = MergeTree()
ORDER BY customer_id;

-- ── 2. products ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.products
(
    product_id UInt32,
    name String,
    category String,
    price Float64,
    stock UInt32
)
ENGINE = MergeTree()
ORDER BY product_id;

-- ── 3. orders ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecommerce.orders
(
    order_id UInt32,
    customer_id UInt32,
    product_id UInt32,
    quantity UInt32,
    order_date Date
)
ENGINE = MergeTree()
ORDER BY (order_date, order_id);

-- ── Insert sample data ──────────────────────────────────────────────────────
INSERT INTO ecommerce.customers (customer_id, name, email, city) VALUES (1, 'Rahul', 'rahul@example.com', 'Mumbai'), (2, 'Priya', 'priya@example.com', 'Delhi'), (3, 'Amit', 'amit@example.com', 'Bangalore'), (4, 'Sneha', 'sneha@example.com', 'Chennai'), (5, 'Vikram', 'vikram@example.com', 'Hyderabad');

INSERT INTO ecommerce.products (product_id, name, category, price, stock) VALUES (101, 'Laptop', 'Electronics', 75000.00, 50), (102, 'Mouse', 'Electronics', 1500.00, 200), (103, 'Keyboard', 'Electronics', 3000.00, 150), (104, 'Headphones', 'Electronics', 5000.00, 100), (105, 'Notebook', 'Stationery', 200.00, 500);

INSERT INTO ecommerce.orders (order_id, customer_id, product_id, quantity, order_date) VALUES (1001, 1, 101, 1, '2026-06-15'), (1002, 1, 102, 2, '2026-06-16'), (1003, 2, 103, 1, '2026-06-16'), (1004, 2, 104, 1, '2026-06-17'), (1005, 3, 105, 5, '2026-06-17'), (1006, 4, 101, 1, '2026-06-18'), (1007, 5, 102, 3, '2026-06-18');
