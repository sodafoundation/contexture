CREATE TABLE IF NOT EXISTS service_dependencies
(
    source_workload String,
    destination_workload String,
    event_time DateTime
)
ENGINE = MergeTree()
ORDER BY (source_workload, event_time);

TRUNCATE TABLE service_dependencies;

INSERT INTO service_dependencies (source_workload, destination_workload, event_time) VALUES
    ('frontend', 'backend', now() - INTERVAL 5 MINUTE),
    ('backend', 'db', now() - INTERVAL 5 MINUTE),
    ('backend', 'frontend', now() - INTERVAL 4 MINUTE),
    ('db', 'backend', now() - INTERVAL 3 MINUTE);
