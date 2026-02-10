Available Tools:
execute_query(query: str, time: Optional[str] = None) -> Dict[str, Any]:
    """Execute an instant query against Prometheus.
    
    Args:
        query: PromQL query string
        time: Optional RFC3339 or Unix timestamp (default: current time)
        
    Returns:
        Query result with type (vector, matrix, scalar, string) and values
    """

execute_range_query(query: str, start: str, end: str, step: str) -> Dict[str, Any]:
    """Execute a range query against Prometheus.
    
    Args:
        query: PromQL query string
        start: Start time as RFC3339 or Unix timestamp
        end: End time as RFC3339 or Unix timestamp
        step: Query resolution step width (e.g., '15s', '1m', '1h')
        
    Returns:
        Range query result with type (usually matrix) and values over time
    """

PromQL Syntax Reference:
- Aggregation operators: sum, min, max, avg, count, stddev, stdvar
- Use "by (label)" to group by labels: max by (cluster_name) (metric_name)
- Use "without (label)" to exclude labels: max without (instance) (metric_name)
- Time ranges: [5m], [1h], [1d] for range vectors
- Rate/increase: rate(metric[5m]), increase(metric[1h])
- Over-time functions: avg_over_time(metric[5m]), max_over_time(metric[1h]), sum_over_time(metric[1d])
- Correct: max by (label) (metric)
- INCORRECT: max over (label) (metric) - "over" is not valid PromQL syntax

IMPORTANT Range Vector Rules:
- Range vectors (e.g., metric[5m]) CANNOT be used directly in aggregations
- INCORRECT: max(process_cpu_seconds_total[5d])
- CORRECT: max(rate(process_cpu_seconds_total[5d])) or max(avg_over_time(process_cpu_seconds_total[5d]))
- Always wrap range vectors with functions like rate(), avg_over_time(), max_over_time(), etc.

CRITICAL - Over-Time Functions REQUIRE Time Ranges:
- Functions like avg_over_time, sum_over_time, max_over_time MUST have a time range
- INCORRECT: avg_over_time(cpu_usage)
- CORRECT: avg_over_time(cpu_usage[5m])
- The time range [5m], [1h], etc. is MANDATORY inside over-time functions