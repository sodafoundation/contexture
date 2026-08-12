# server.py — Prometheus MCP Server for SODA Contexture
#
# Implements the FastMCP @app.tool() pattern, consistent with other
# SODA Contexture data-connector agents (postgres, clickhouse, etc.).
# Connects to Prometheus instances defined in config/prometheus_config.yaml.
#
# Run (always from the pkg/agents/prometheus/ directory):
#   python server.py                          # stdio transport (default)
#   python server.py --transport sse          # SSE/HTTP on port 8001
#   python server.py --transport sse --port 9001  # custom port

import os
import yaml
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import numpy as np
from fastmcp import FastMCP
from prometheus_connector import get_all_instances, get_client

app = FastMCP("Prometheus MCP Server")


# ── helpers ───────────────────────────────────────────────────────────────────

def _instances() -> List[Dict]:
    """Lazy-load all configured Prometheus instances."""
    try:
        return get_all_instances()
    except FileNotFoundError as e:
        print(f"[prometheus-mcp] WARNING: {e}")
        return []


def _resolve_repo_path(*parts: str) -> str:
    """Resolve a path relative to the repo root.
    server.py lives at pkg/agents/prometheus/server.py — three levels up is root.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    return os.path.join(repo_root, *parts)


# ── tools ─────────────────────────────────────────────────────────────────────

@app.tool()
def explain_ocs_policy(
    config_path: str = "pkg/ocs/ocs_config.yaml",
    output_format: str = "bullets",
) -> Dict[str, Any]:
    """
    Explain OCS policy configuration in a structured way.

    Args:
        config_path:   Path to the OCS config YAML (repo-relative by default).
        output_format: "bullets" | "plain" | "json"
    """
    if output_format not in {"bullets", "plain", "json"}:
        return {"error": f"Invalid output_format '{output_format}' (expected bullets|plain|json)"}

    resolved_path = config_path if os.path.isabs(config_path) else _resolve_repo_path(config_path)

    if not os.path.exists(resolved_path):
        return {"error": f"OCS config not found at {resolved_path}"}

    try:
        with open(resolved_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        return {"error": f"Failed to read OCS config: {str(e)}"}

    policy_raw = cfg.get("policy") or []
    if isinstance(policy_raw, str):
        policy_raw = [policy_raw]

    metrics = cfg.get("metrics") or []
    if not isinstance(metrics, list):
        metrics = []

    derived_checks: List[Dict[str, Any]] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        health = m.get("health_config") or {}
        if not isinstance(health, dict):
            health = {}
        threshold = health.get("critical_threshold")
        polarity = health.get("polarity")
        metric_name = m.get("name")
        unit = m.get("unit")
        if threshold is None:
            continue
        if polarity == "high_is_bad":
            condition = f"{metric_name} > {threshold}{unit or ''}"
        elif polarity == "low_is_bad":
            condition = f"{metric_name} < {threshold}{unit or ''}"
        else:
            condition = f"{metric_name} crosses {threshold}{unit or ''}"
        derived_checks.append({
            "metric": metric_name,
            "metric_type": m.get("type"),
            "unit": unit,
            "critical_threshold": threshold,
            "polarity": polarity,
            "condition": condition,
        })

    time_window_minutes = cfg.get("time_window_minutes")
    workloads = cfg.get("workload") or []
    if isinstance(workloads, str):
        workloads = [workloads]

    lines: List[str] = []
    if policy_raw:
        lines.append("Policy statements:")
        lines.extend(f"- {p}" for p in policy_raw)
    if derived_checks:
        lines.append("Derived metric checks (from metrics.health_config):")
        lines.extend(f"- {c['condition']}" for c in derived_checks)
    if workloads:
        lines.append(f"Configured workloads: {', '.join(workloads)}")
    if time_window_minutes is not None:
        lines.append(f"Prometheus query time window (minutes): {time_window_minutes}")

    if output_format == "plain":
        explanation: Union[str, List[str], Dict[str, Any]] = "\n".join(lines).strip()
    elif output_format == "bullets":
        explanation = lines
    else:
        explanation = {
            "policy": policy_raw,
            "derived_checks": derived_checks,
            "workloads": workloads,
            "time_window_minutes": time_window_minutes,
        }

    return {
        "policy_raw": policy_raw,
        "derived_checks": derived_checks,
        "workloads": workloads,
        "time_window_minutes": time_window_minutes,
        "explanation": explanation,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def current_metric_for_pods(
    metric_name: str = "container_cpu_usage_seconds_total",
    pod_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get the current value of a metric for a list of pods.

    Args:
        metric_name: PromQL metric name.
        pod_names:   List of pod names to query.
    """
    if not pod_names:
        return {"error": "pod_names must be provided"}

    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        results = []
        try:
            for pod_name in pod_names:
                query = f"{metric_name}{{pod='{pod_name}'}}"
                response = client.custom_query(query=query)
                value = None
                if response:
                    try:
                        value = float(response[0]["value"][1])
                    except (KeyError, ValueError, IndexError):
                        pass
                results.append({"pod": pod_name, "query": query, "value": value})
        except Exception as e:
            all_results[name] = {"error": str(e)}
            continue
        all_results[name] = results

    return {
        "metric": metric_name,
        "pods_current_metric_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def workload_metrics(
    metric_name: str = "container_cpu_usage_seconds_total",
    workload_name: Optional[str] = None,
    pod_names: Optional[List[str]] = None,
    time_window: Optional[str] = None,
    aggregation: str = "avg",
) -> Dict[str, Any]:
    """
    Query workload-level gauge metrics from Prometheus.
    Aggregates across pods; supports optional time window.

    Args:
        metric_name:   PromQL metric name.
        workload_name: Value of the 'app' label for this workload.
        pod_names:     Optional list of pod names to narrow the query.
        time_window:   PromQL range (e.g. '5m', '1h'). Omit for instant query.
        aggregation:   One of avg | max | min | sum (default: avg).
    """
    if not workload_name:
        return {"error": "workload_name (app label) must be provided"}
    if aggregation not in {"avg", "max", "min", "sum"}:
        return {"error": f"Invalid aggregation '{aggregation}'"}

    label_filters = [f'app="{workload_name}"']
    if pod_names:
        label_filters.append(f'pod=~"{"|".join(pod_names)}"')
    label_selector = ",".join(label_filters)

    if time_window:
        query = f"{aggregation}({aggregation}_over_time({metric_name}{{{label_selector}}}[{time_window}]))"
        effective_window = time_window
    else:
        query = f"{aggregation}({metric_name}{{{label_selector}}})"
        effective_window = "current"

    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            response = client.custom_query(query=query)
            value = None
            if response:
                try:
                    value = float(response[0]["value"][1])
                except (KeyError, ValueError, IndexError):
                    pass
            all_results[name] = {"query": query, "value": value}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "metric": metric_name,
        "metric_type": "gauge",
        "workload": workload_name,
        "pods_filtered": pod_names or "ALL",
        "aggregation": aggregation,
        "time_window": effective_window,
        "results_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def top_n_pods_by_metric(
    metric_name: str = "container_cpu_usage_seconds_total",
    top_n: int = 5,
    window: str = "30m",
) -> Dict[str, Any]:
    """
    Return the top N pods by average metric value over a time window.

    Args:
        metric_name: PromQL metric name.
        top_n:       Number of pods to return (default: 5).
        window:      Lookback window (default: '30m').
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f'topk({top_n}, avg_over_time({metric_name}{{pod!=""}}[{window}]))'
            result = client.custom_query(query=query)
            pods_info = []
            for item in result:
                pod_name = item.get("metric", {}).get("pod")
                value = float(item.get("value", [0, "0"])[1])
                if pod_name:
                    pods_info.append({"pod": pod_name, "value": value})
            pods_info.sort(key=lambda x: x["value"], reverse=True)
            all_results[name] = pods_info
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "metric": metric_name,
        "window": window,
        "pods_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pod_network_io(pod_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Return network receive/transmit rates (bytes/sec) for given pods.

    Args:
        pod_names: List of pod names to query.
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            results = []
            for pod_name in pod_names or []:
                rx = client.custom_query(f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[5m])')
                tx = client.custom_query(f'rate(container_network_transmit_bytes_total{{pod="{pod_name}"}}[5m])')
                results.append({
                    "pod": pod_name,
                    "rx_bytes_per_sec": float(rx[0]["value"][1]) if rx else 0,
                    "tx_bytes_per_sec": float(tx[0]["value"][1]) if tx else 0,
                })
            all_results[name] = results
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pod_network_io_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pods_exceeding_cpu(threshold: float = 0.8) -> Dict[str, Any]:
    """
    List pods whose CPU rate exceeds the given threshold.

    Args:
        threshold: CPU cores/sec threshold (default: 0.8).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f"rate(container_cpu_usage_seconds_total[5m]) > {threshold}")
            pods = [
                {"pod": item["metric"]["pod"], "cpu_value": float(item["value"][1])}
                for item in result if "pod" in item["metric"]
            ]
            all_results[name] = pods
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pods_exceeding_cpu_per_prometheus": all_results,
        "threshold": threshold,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pods_exceeding_memory(threshold_bytes: float = 1073741824) -> Dict[str, Any]:
    """
    List pods whose memory usage exceeds the given threshold.

    Args:
        threshold_bytes: Memory threshold in bytes (default: 1 GiB).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f"container_memory_usage_bytes > {threshold_bytes}")
            pods = [
                {"pod": item["metric"].get("pod"), "memory_bytes": float(item["value"][1])}
                for item in result if "pod" in item["metric"]
            ]
            all_results[name] = pods
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pods_exceeding_memory_per_prometheus": all_results,
        "threshold_bytes": threshold_bytes,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pod_status_summary() -> Dict[str, Any]:
    """
    Return a count of pods in each lifecycle phase (Running, Pending, Failed, etc.)
    across all configured Prometheus instances.
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query("sum(kube_pod_status_phase) by (phase)")
            summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            summary["total"] = sum(summary.values())
            all_results[name] = summary
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pod_status_summary_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def list_all_pods(namespace: Optional[str] = None) -> Dict[str, Any]:
    """
    List all Kubernetes pods with their namespace, node, and phase.
    Uses kube_pod_info to enumerate every pod in the cluster.

    Args:
        namespace: Optional namespace filter (e.g. 'default'). If empty, returns all namespaces.
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            if namespace:
                query = f'kube_pod_info{{namespace="{namespace}"}}'
            else:
                query = "kube_pod_info"
            result = client.custom_query(query=query)
            pods = []
            seen = set()
            for item in result:
                metric = item.get("metric", {})
                pod_name = metric.get("pod", "")
                if pod_name in seen:
                    continue
                seen.add(pod_name)
                pods.append({
                    "pod": pod_name,
                    "namespace": metric.get("namespace", ""),
                    "node": metric.get("node", ""),
                    "created_by_kind": metric.get("created_by_kind", ""),
                    "created_by_name": metric.get("created_by_name", ""),
                })
            pods.sort(key=lambda x: (x["namespace"], x["pod"]))
            all_results[name] = {
                "total_pods": len(pods),
                "pods": pods,
            }
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "list_all_pods_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def recent_pod_events(limit: int = 10) -> Dict[str, Any]:
    """
    Return the most recent Kubernetes pod events (by reason + object).

    Args:
        limit: Maximum number of events to return (default: 10).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "sort_desc(sum by (reason, involved_object_name) (increase(kube_event_count[10m])))"
            result = client.custom_query(query=query)
            events = [
                {
                    "pod": item.get("metric", {}).get("involved_object_name"),
                    "reason": item.get("metric", {}).get("reason"),
                    "count": int(float(item["value"][1])),
                }
                for item in result[:limit]
            ]
            all_results[name] = events
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "recent_pod_events_per_prometheus": all_results,
        "lookback": "10m",
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def node_disk_usage(window_minutes: int = 20) -> Dict[str, Any]:
    """
    Return average and peak disk usage (%) per node for important mount points.

    Args:
        window_minutes: Lookback window in minutes (default: 20).
    """
    important_mounts = {"/", "/var/lib", "/data"}
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=window_minutes)

    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))'
            
            # Dynamically calculate step to avoid exceeding Prometheus limit of 11,000 points
            step_size = "1m"
            if window_minutes > 1000:
                step_size = f"{max(1, window_minutes // 500)}m"

            result = client.custom_query_range(
                query=query, start_time=start_time, end_time=end_time, step=step_size
            )
            disk_usage = []
            for item in result:
                metric = item.get("metric", {})
                mount = metric.get("mountpoint", "")
                if mount not in important_mounts:
                    continue
                values = [float(v[1]) for v in item.get("values", [])]
                if not values:
                    continue
                disk_usage.append({
                    "node": metric.get("node", "unknown"),
                    "mount": mount,
                    "cluster": metric.get("cluster", "unknown"),
                    "region": metric.get("region", "unknown"),
                    "environment": metric.get("environment", "unknown"),
                    "avg_disk_usage_percent": round(sum(values) / len(values), 2),
                    "max_disk_usage_percent": round(max(values), 2),
                })
            disk_usage.sort(key=lambda x: x["max_disk_usage_percent"], reverse=True)
            all_results[name] = {
                "window_minutes": window_minutes,
                "top_nodes": disk_usage[:10],
            }
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "node_disk_usage_per_prometheus": all_results,
        "fetched_at": datetime.utcnow().isoformat(),
    }


@app.tool()
def node_memory_usage(window_minutes: int = 20) -> Dict[str, Any]:
    """
    Return average and peak memory usage (%) per node.

    Args:
        window_minutes: Lookback window in minutes (default: 20).
    """
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=window_minutes)

    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "100 * (1 - ((node_memory_MemFree_bytes + node_memory_Buffers_bytes + node_memory_Cached_bytes) / node_memory_MemTotal_bytes))"
            
            # Dynamically calculate step to avoid exceeding Prometheus limit of 11,000 points
            step_size = "1m"
            if window_minutes > 1000:
                step_size = f"{max(1, window_minutes // 500)}m"

            result = client.custom_query_range(
                query=query, start_time=start_time, end_time=end_time, step=step_size
            )
            memory_usage = []
            for item in result:
                node = item.get("metric", {}).get("instance", item.get("metric", {}).get("node", "unknown"))
                values = [float(v[1]) for v in item.get("values", [])]
                if not values:
                    continue
                memory_usage.append({
                    "node": node,
                    "avg_memory_usage_percent": round(sum(values) / len(values), 2),
                    "max_memory_usage_percent": round(max(values), 2),
                })
            memory_usage.sort(key=lambda x: x["max_memory_usage_percent"], reverse=True)
            all_results[name] = {"window_minutes": window_minutes, "top_nodes": memory_usage[:10]}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "node_memory_usage_per_prometheus": all_results,
        "fetched_at": datetime.utcnow().isoformat(),
    }


@app.tool()
def top_memory_pressure_nodes(threshold: float = 80.0, top_n: int = 5) -> Dict[str, Any]:
    """
    List the nodes with memory usage above the given threshold.

    Args:
        threshold: Memory usage % threshold (default: 80.0).
        top_n:     Maximum number of nodes to return (default: 5).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "100 * (1 - ((node_memory_MemFree_bytes + node_memory_Buffers_bytes + node_memory_Cached_bytes) / node_memory_MemTotal_bytes))"
            result = client.custom_query(query=query)
            nodes_info = [
                {"node": item.get("metric", {}).get("instance", item.get("metric", {}).get("node")),
                 "usage_percent": round(float(item.get("value", [0, "0"])[1]), 2)}
                for item in result
                if float(item.get("value", [0, "0"])[1]) >= threshold
            ]
            nodes_info.sort(key=lambda x: x["usage_percent"], reverse=True)
            nodes_info = nodes_info[:top_n]
            msg = (f"{len(nodes_info)} node(s) above {threshold}% memory usage."
                   if nodes_info else "No nodes are under memory pressure.")
            all_results[name] = {"nodes": nodes_info, "message": msg, "threshold": threshold}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "top_memory_pressure_nodes_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def describe_cluster_health() -> Dict[str, Any]:
    """
    Return a plain-English cluster health summary based on pod phase counts.
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query("sum(kube_pod_status_phase) by (phase)")
            summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            total = sum(summary.values())
            running = summary.get("Running", 0)
            pending = summary.get("Pending", 0)
            failed = summary.get("Failed", 0)
            if failed > 0:
                msg = f"{failed} pod(s) failing. {running}/{total} running."
            elif pending > 0:
                msg = f"{pending} pod(s) pending. {running}/{total} running."
            else:
                msg = f"All systems nominal: {running}/{total} pods healthy."
            all_results[name] = {"summary": summary, "message": msg}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "cluster_health_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def top_disk_pressure_nodes(threshold: float = 80.0, top_n: int = 5) -> Dict[str, Any]:
    """
    List the nodes with disk usage above the given threshold.

    Args:
        threshold: Disk usage % threshold (default: 80.0).
        top_n:     Maximum number of nodes to return (default: 5).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))'
            result = client.custom_query(query=query)
            nodes_info = []
            for item in result:
                metric = item.get("metric", {})
                usage = float(item.get("value", [0, "0"])[1])
                if usage >= threshold:
                    nodes_info.append({
                        "node": metric.get("instance"),
                        "mount": metric.get("mountpoint", ""),
                        "usage_percent": round(usage, 2),
                    })
            nodes_info.sort(key=lambda x: x["usage_percent"], reverse=True)
            nodes_info = nodes_info[:top_n]
            msg = (f"{len(nodes_info)} node(s) above {threshold}% disk usage."
                   if nodes_info else "No nodes are under disk pressure.")
            all_results[name] = {"nodes": nodes_info, "message": msg, "threshold": threshold}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "top_disk_pressure_nodes_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pod_restart_trend(window: str = "30m", top_n: int = 5) -> Dict[str, Any]:
    """
    Return pods with the highest restart counts over a recent time window.

    Args:
        window: Lookback window (default: '30m').
        top_n:  Number of pods to return (default: 5).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f"topk({top_n}, increase(kube_pod_container_status_restarts_total[{window}]))"
            result = client.custom_query(query=query)
            trends = []
            for item in result:
                metric = item.get("metric", {})
                pod = metric.get("pod")
                if pod:
                    trends.append({
                        "pod": pod,
                        "container": metric.get("container", ""),
                        "restarts": float(item.get("value", [0, "0"])[1]),
                    })
            trends.sort(key=lambda x: x["restarts"], reverse=True)
            msg = (f"Pods with recent restarts detected (last {window})."
                   if trends else f"No recent restarts in the last {window}.")
            all_results[name] = {"pods": trends, "message": msg, "window": window}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pod_restart_trend_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def detect_pod_anomalies(
    metric_name: str = "container_cpu_usage_seconds_total",
    z_threshold: float = 3.0,
) -> Dict[str, Any]:
    """
    Detect pods with anomalous metric values using Z-score analysis.

    Args:
        metric_name: PromQL metric name (default: container_cpu_usage_seconds_total).
        z_threshold: Z-score cutoff for anomaly classification (default: 3.0).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f'avg_over_time({metric_name}{{pod!=""}}[15m])')
            values = [float(r["value"][1]) for r in result]
            if not values:
                all_results[name] = {"message": "No data"}
                continue
            mean = sum(values) / len(values)
            std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
            anomalies = []
            for r in result:
                pod = r["metric"].get("pod")
                val = float(r["value"][1])
                z = (val - mean) / std if std > 0 else 0
                if abs(z) > z_threshold:
                    anomalies.append({"pod": pod, "value": val, "z_score": round(z, 2)})
            all_results[name] = {"anomalies": anomalies, "mean": mean, "std": std}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pod_anomalies_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def namespace_resource_summary(resource: str = "cpu", window: str = "5m") -> Dict[str, Any]:
    """
    Return CPU or memory usage broken down by namespace.

    Args:
        resource: "cpu" or "memory" (default: cpu).
        window:   Rate window (default: '5m').
    """
    metric = (
        "container_cpu_usage_seconds_total" if resource == "cpu"
        else "container_memory_usage_bytes"
    )
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f'sum(rate({metric}{{namespace!=""}}[{window}])) by (namespace)'
            result = client.custom_query(query=query)
            usage = [
                {"namespace": r["metric"]["namespace"], "value": float(r["value"][1])}
                for r in result
            ]
            total = sum(x["value"] for x in usage)
            for x in usage:
                x["percent_of_total"] = round((x["value"] / total) * 100, 2) if total > 0 else 0
            usage.sort(key=lambda x: x["value"], reverse=True)
            all_results[name] = {"resource": resource, "usage_by_namespace": usage}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "namespace_resource_summary_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def detect_crashloop_pods(window: str = "10m", threshold: int = 2) -> Dict[str, Any]:
    """
    Detect pods in or approaching CrashLoopBackOff.

    Args:
        window:    Lookback window (default: '10m').
        threshold: Minimum restart count to flag (default: 2).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f"increase(kube_pod_container_status_restarts_total[{window}]) > {threshold}"
            result = client.custom_query(query=query)
            pods = [
                {"pod": r["metric"]["pod"], "restarts": int(float(r["value"][1]))}
                for r in result if "pod" in r["metric"]
            ]
            all_results[name] = {"crashloop_pods": pods, "window": window}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "crashloop_pods_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def correlate_metrics(
    metric_a: str = "container_cpu_usage_seconds_total",
    metric_b: str = "container_network_receive_bytes_total",
    window: str = "10m",
) -> Dict[str, Any]:
    """
    Compute the Pearson correlation between two metrics across pods.

    Args:
        metric_a: First PromQL metric name.
        metric_b: Second PromQL metric name.
        window:   Rate window for both metrics (default: '10m').
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            r1 = client.custom_query(f"rate({metric_a}[{window}])")
            r2 = client.custom_query(f"rate({metric_b}[{window}])")
            data_a = {r["metric"].get("pod"): float(r["value"][1]) for r in r1 if "pod" in r["metric"]}
            data_b = {r["metric"].get("pod"): float(r["value"][1]) for r in r2 if "pod" in r["metric"]}
            common = set(data_a) & set(data_b)
            if not common:
                all_results[name] = {"message": "No overlapping pods between the two metrics"}
                continue
            pairs = [(data_a[p], data_b[p]) for p in common]
            corr = float(np.corrcoef([x for x, _ in pairs], [y for _, y in pairs])[0, 1])
            all_results[name] = {
                "correlation": round(corr, 3),
                "metric_a": metric_a,
                "metric_b": metric_b,
                "window": window,
                "pod_count": len(common),
            }
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "correlation_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def pod_event_timeline(pod_name: str, window: str = "30m") -> Dict[str, Any]:
    """
    Return a snapshot of restarts, network I/O, and CPU for a specific pod.

    Args:
        pod_name: Name of the pod to inspect.
        window:   Lookback window (default: '30m').
    """
    queries = {
        "restarts": f'increase(kube_pod_container_status_restarts_total{{pod="{pod_name}"}}[{window}])',
        "network_rx": f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[{window}])',
        "cpu": f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}"}}[{window}])',
    }
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            timeline = {}
            for key, q in queries.items():
                result = client.custom_query(q)
                if result:
                    timeline[key] = float(result[0]["value"][1])
            all_results[name] = {"pod": pod_name, "timeline": timeline, "window": window}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "pod_event_timeline_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def node_condition_summary() -> Dict[str, Any]:
    """
    Return nodes with non-Ready conditions (e.g. MemoryPressure, DiskPressure, PIDPressure).
    """
    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = 'kube_node_status_condition{status="true", condition!="Ready"}'
            result = client.custom_query(query=query)
            issues = [
                {"node": r["metric"]["node"], "condition": r["metric"]["condition"]}
                for r in result
            ]
            all_results[name] = {"node_issues": issues}
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "node_condition_summary_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def query_custom_metric_range(metric_name: str, window: str = "30d", step: Optional[str] = None) -> Dict[str, Any]:
    """
    Query any arbitrary Prometheus metric over a range window.

    Args:
        metric_name: The raw name of the Prometheus metric to query (e.g. 'kube_node_status_capacity_cpu_cores').
        window: Range window lookback (e.g. '30d', '8w', '24h'). Default: '30d'.
        step: Optional resolution step size (e.g. '1h'). If not provided, it is scaled dynamically.
    """
    import re
    minutes = 43200
    match = re.match(r"(\d+)([wdhm])", window.lower())
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        if unit == "w":
            minutes = val * 7 * 24 * 60
        elif unit == "d":
            minutes = val * 24 * 60
        elif unit == "h":
            minutes = val * 60
        elif unit == "m":
            minutes = val

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes)

    all_results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            step_size = step
            if not step_size:
                step_size = "1m"
                if minutes > 1000:
                    step_size = f"{max(1, minutes // 500)}m"

            result = client.custom_query_range(
                query=metric_name, start_time=start_time, end_time=end_time, step=step_size
            )
            formatted_data = []
            for item in result:
                metric_labels = item.get("metric", {})
                values = item.get("values", [])
                if not values:
                    continue
                val_floats = [float(v[1]) for v in values]
                formatted_data.append({
                    "labels": metric_labels,
                    "avg_value": round(sum(val_floats) / len(val_floats), 2),
                    "min_value": round(min(val_floats), 2),
                    "max_value": round(max(val_floats), 2),
                    "latest_value": round(val_floats[-1], 2),
                    "points_count": len(val_floats)
                })
            all_results[name] = formatted_data
        except Exception as e:
            all_results[name] = {"error": str(e)}

    return {
        "metric": metric_name,
        "window": window,
        "results": all_results,
        "timestamp": datetime.now().isoformat()
    }


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prometheus MCP Server for SODA Contexture")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport type (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for SSE transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        app.run(transport="sse", port=args.port)
    else:
        app.run()
