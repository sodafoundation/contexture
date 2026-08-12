"""
MCP tool wrapper functions for the Prometheus agent.

Each function corresponds to one @app.tool() in server.py.
Separated here so they can be called directly (e.g. from agent.py or tests)
without starting the full FastMCP server.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from prometheus_connector import get_all_instances, get_client


def _instances():
    return get_all_instances()


# ── tools ─────────────────────────────────────────────────────────────────────

def workload_metrics_tool(
    metric_name: str = "container_cpu_usage_seconds_total",
    workload_name: Optional[str] = None,
    pod_names: Optional[List[str]] = None,
    time_window: Optional[str] = None,
    aggregation: str = "avg",
) -> Dict[str, Any]:
    if not workload_name:
        return {"error": "workload_name must be provided"}
    if workload_name.startswith("workload-"):
        workload_name = workload_name[len("workload-"):]
    if aggregation not in {"avg", "max", "min", "sum"}:
        return {"error": f"Invalid aggregation '{aggregation}'"}

    label_filters = [f'app="{workload_name}"']
    if pod_names:
        label_filters.append(f'pod=~"{"|".join(pod_names)}"')
    label_selector = ",".join(label_filters)

    if time_window:
        query = f"{aggregation}({aggregation}_over_time({metric_name}{{{label_selector}}}[{time_window}]))"
    else:
        query = f"{aggregation}({metric_name}{{{label_selector}}})"

    results = {}
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
            results[name] = {"query": query, "value": value}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def top_n_pods_by_metric_tool(
    metric_name: str = "container_cpu_usage_seconds_total",
    top_n: int = 5,
    window: str = "30m",
) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f'topk({top_n}, avg_over_time({metric_name}{{pod!=""}}[{window}]))'
            result = client.custom_query(query=query)
            pods_info = [
                {"pod": item.get("metric", {}).get("pod"), "value": float(item.get("value", [0, "0"])[1])}
                for item in result if item.get("metric", {}).get("pod")
            ]
            pods_info.sort(key=lambda x: x["value"], reverse=True)
            results[name] = pods_info
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pods_exceeding_cpu_tool(threshold: float = 0.8) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f"rate(container_cpu_usage_seconds_total[5m]) > {threshold}")
            results[name] = [
                {"pod": item["metric"]["pod"], "cpu_value": float(item["value"][1])}
                for item in result if "pod" in item["metric"]
            ]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pods_exceeding_memory_tool(threshold_bytes: float = 1073741824) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f"container_memory_usage_bytes > {threshold_bytes}")
            results[name] = [
                {"pod": item["metric"].get("pod"), "memory_bytes": float(item["value"][1])}
                for item in result if "pod" in item["metric"]
            ]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pod_status_summary_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query("sum(kube_pod_status_phase) by (phase)")
            summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            summary["total"] = sum(summary.values())
            results[name] = summary
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def node_disk_usage_tool(window_minutes: int = 20) -> Dict[str, Any]:
    important_mounts = {"/", "/var/lib", "/data"}
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=window_minutes)
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))'
            result = client.custom_query_range(query=query, start_time=start_time, end_time=end_time, step="1m")
            disk_usage = []
            for item in result:
                metric = item.get("metric", {})
                if metric.get("mountpoint", "") not in important_mounts:
                    continue
                values = [float(v[1]) for v in item.get("values", [])]
                if values:
                    disk_usage.append({
                        "node": metric.get("node", "unknown"),
                        "mount": metric.get("mountpoint"),
                        "avg_disk_usage_percent": round(sum(values) / len(values), 2),
                        "max_disk_usage_percent": round(max(values), 2),
                    })
            disk_usage.sort(key=lambda x: x["max_disk_usage_percent"], reverse=True)
            results[name] = disk_usage[:10]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def node_memory_usage_tool(window_minutes: int = 20) -> Dict[str, Any]:
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=window_minutes)
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "100 * (1 - ((node_memory_MemFree_bytes + node_memory_Buffers_bytes + node_memory_Cached_bytes) / node_memory_MemTotal_bytes))"
            result = client.custom_query_range(query=query, start_time=start_time, end_time=end_time, step="1m")
            memory_usage = []
            for item in result:
                node = item.get("metric", {}).get("instance", item.get("metric", {}).get("node", "unknown"))
                values = [float(v[1]) for v in item.get("values", [])]
                if values:
                    memory_usage.append({
                        "node": node,
                        "avg_memory_usage_percent": round(sum(values) / len(values), 2),
                        "max_memory_usage_percent": round(max(values), 2),
                    })
            memory_usage.sort(key=lambda x: x["max_memory_usage_percent"], reverse=True)
            results[name] = memory_usage[:10]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def describe_cluster_health_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query("sum(kube_pod_status_phase) by (phase)")
            summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            total = sum(summary.values())
            running = summary.get("Running", 0)
            failed = summary.get("Failed", 0)
            pending = summary.get("Pending", 0)
            if failed > 0:
                msg = f"{failed} pod(s) failing. {running}/{total} running."
            elif pending > 0:
                msg = f"{pending} pod(s) pending. {running}/{total} running."
            else:
                msg = f"All systems nominal: {running}/{total} pods healthy."
            results[name] = {"summary": summary, "message": msg}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def top_disk_pressure_nodes_tool(threshold: float = 80.0, top_n: int = 5) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))'
            result = client.custom_query(query=query)
            nodes_info = [
                {"node": item.get("metric", {}).get("instance"), "mount": item.get("metric", {}).get("mountpoint", ""), "usage_percent": round(float(item.get("value", [0, "0"])[1]), 2)}
                for item in result if float(item.get("value", [0, "0"])[1]) >= threshold
            ]
            nodes_info.sort(key=lambda x: x["usage_percent"], reverse=True)
            results[name] = nodes_info[:top_n]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def top_memory_pressure_nodes_tool(threshold: float = 80.0, top_n: int = 5) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "100 * (1 - ((node_memory_MemFree_bytes + node_memory_Buffers_bytes + node_memory_Cached_bytes) / node_memory_MemTotal_bytes))"
            result = client.custom_query(query=query)
            nodes_info = [
                {"node": item.get("metric", {}).get("instance", item.get("metric", {}).get("node")), "usage_percent": round(float(item.get("value", [0, "0"])[1]), 2)}
                for item in result if float(item.get("value", [0, "0"])[1]) >= threshold
            ]
            nodes_info.sort(key=lambda x: x["usage_percent"], reverse=True)
            results[name] = nodes_info[:top_n]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pod_restart_trend_tool(window: str = "30m", top_n: int = 5) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f"topk({top_n}, increase(kube_pod_container_status_restarts_total[{window}]))"
            result = client.custom_query(query=query)
            trends = [
                {"pod": item.get("metric", {}).get("pod"), "container": item.get("metric", {}).get("container", ""), "restarts": float(item.get("value", [0, "0"])[1])}
                for item in result if item.get("metric", {}).get("pod")
            ]
            trends.sort(key=lambda x: x["restarts"], reverse=True)
            results[name] = trends
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def detect_pod_anomalies_tool(
    metric_name: str = "container_cpu_usage_seconds_total",
    z_threshold: float = 3.0,
) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            result = client.custom_query(f'avg_over_time({metric_name}{{pod!=""}}[15m])')
            values = [float(r["value"][1]) for r in result]
            if not values:
                results[name] = {"message": "No data"}
                continue
            mean = sum(values) / len(values)
            std = (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5
            anomalies = [
                {"pod": r["metric"].get("pod"), "value": float(r["value"][1]), "z_score": round((float(r["value"][1]) - mean) / std if std > 0 else 0, 2)}
                for r in result if abs((float(r["value"][1]) - mean) / std if std > 0 else 0) > z_threshold
            ]
            results[name] = {"anomalies": anomalies, "mean": mean, "std": std}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def detect_crashloop_pods_tool(window: str = "10m", threshold: int = 2) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = f"increase(kube_pod_container_status_restarts_total[{window}]) > {threshold}"
            result = client.custom_query(query=query)
            results[name] = [
                {"pod": r["metric"]["pod"], "restarts": int(float(r["value"][1]))}
                for r in result if "pod" in r["metric"]
            ]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pod_event_timeline_tool(pod_name: str, window: str = "30m") -> Dict[str, Any]:
    queries = {
        "restarts": f'increase(kube_pod_container_status_restarts_total{{pod="{pod_name}"}}[{window}])',
        "network_rx": f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[{window}])',
        "cpu": f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}"}}[{window}])',
    }
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            timeline = {}
            for key, q in queries.items():
                result = client.custom_query(q)
                if result:
                    timeline[key] = float(result[0]["value"][1])
            results[name] = {"pod": pod_name, "timeline": timeline, "window": window}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def node_condition_summary_tool() -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = 'kube_node_status_condition{status="true", condition!="Ready"}'
            result = client.custom_query(query=query)
            results[name] = [
                {"node": r["metric"]["node"], "condition": r["metric"]["condition"]}
                for r in result
            ]
        except Exception as e:
            results[name] = {"error": str(e)}


def current_metric_for_pods_tool(
    metric_name: str = "container_cpu_usage_seconds_total",
    pod_names=None,
) -> dict:
    if not pod_names:
        return {"error": "pod_names must be provided"}
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        pod_results = []
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
                pod_results.append({"pod": pod_name, "query": query, "value": value})
            results[name] = pod_results
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pod_network_io_tool(pod_names=None) -> dict:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            io_results = []
            for pod_name in pod_names or []:
                rx = client.custom_query(
                    f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[5m])'
                )
                tx = client.custom_query(
                    f'rate(container_network_transmit_bytes_total{{pod="{pod_name}"}}[5m])'
                )
                io_results.append({
                    "pod": pod_name,
                    "rx_bytes_per_sec": float(rx[0]["value"][1]) if rx else 0,
                    "tx_bytes_per_sec": float(tx[0]["value"][1]) if tx else 0,
                })
            results[name] = io_results
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def recent_pod_events_tool(limit: int = 10) -> dict:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "sort_desc(sum by (reason, involved_object_name) (increase(kube_event_count[10m])))"
            result = client.custom_query(query=query)
            results[name] = [
                {
                    "pod": item.get("metric", {}).get("involved_object_name"),
                    "reason": item.get("metric", {}).get("reason"),
                    "count": int(float(item["value"][1])),
                }
                for item in result[:limit]
            ]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def namespace_resource_summary_tool(resource: str = "cpu", window: str = "5m") -> dict:
    metric = (
        "container_cpu_usage_seconds_total" if resource == "cpu"
        else "container_memory_usage_bytes"
    )
    results = {}
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
            results[name] = {"resource": resource, "usage_by_namespace": usage}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def correlate_metrics_tool(
    metric_a: str = "container_cpu_usage_seconds_total",
    metric_b: str = "container_network_receive_bytes_total",
    window: str = "10m",
) -> dict:
    import numpy as np
    results = {}
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
                results[name] = {"message": "No overlapping pods between the two metrics"}
                continue
            pairs = [(data_a[p], data_b[p]) for p in common]
            corr = float(np.corrcoef([x for x, _ in pairs], [y for _, y in pairs])[0, 1])
            results[name] = {
                "correlation": round(corr, 3),
                "metric_a": metric_a,
                "metric_b": metric_b,
                "window": window,
                "pod_count": len(common),
            }
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def current_metric_for_pods_tool(
    metric_name: str = "container_cpu_usage_seconds_total",
    pod_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not pod_names:
        return {"error": "pod_names must be provided"}
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        pod_results = []
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
                pod_results.append({"pod": pod_name, "query": query, "value": value})
            results[name] = pod_results
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def pod_network_io_tool(pod_names: Optional[List[str]] = None) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            io_results = []
            for pod_name in pod_names or []:
                rx = client.custom_query(f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[5m])')
                tx = client.custom_query(f'rate(container_network_transmit_bytes_total{{pod="{pod_name}"}}[5m])')
                io_results.append({
                    "pod": pod_name,
                    "rx_bytes_per_sec": float(rx[0]["value"][1]) if rx else 0,
                    "tx_bytes_per_sec": float(tx[0]["value"][1]) if tx else 0,
                })
            results[name] = io_results
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def recent_pod_events_tool(limit: int = 10) -> Dict[str, Any]:
    results = {}
    for inst in _instances():
        name = inst["name"]
        client = get_client(inst)
        try:
            query = "sort_desc(sum by (reason, involved_object_name) (increase(kube_event_count[10m])))"
            result = client.custom_query(query=query)
            results[name] = [
                {
                    "pod": item.get("metric", {}).get("involved_object_name"),
                    "reason": item.get("metric", {}).get("reason"),
                    "count": int(float(item["value"][1])),
                }
                for item in result[:limit]
            ]
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def namespace_resource_summary_tool(resource: str = "cpu", window: str = "5m") -> Dict[str, Any]:
    metric = (
        "container_cpu_usage_seconds_total" if resource == "cpu"
        else "container_memory_usage_bytes"
    )
    results = {}
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
            results[name] = {"resource": resource, "usage_by_namespace": usage}
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def correlate_metrics_tool(
    metric_a: str = "container_cpu_usage_seconds_total",
    metric_b: str = "container_network_receive_bytes_total",
    window: str = "10m",
) -> Dict[str, Any]:
    results = {}
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
                results[name] = {"message": "No overlapping pods between the two metrics"}
                continue
            pairs = [(data_a[p], data_b[p]) for p in common]
            corr = float(np.corrcoef([x for x, _ in pairs], [y for _, y in pairs])[0, 1])
            results[name] = {
                "correlation": round(corr, 3),
                "metric_a": metric_a,
                "metric_b": metric_b,
                "window": window,
                "pod_count": len(common),
            }
        except Exception as e:
            results[name] = {"error": str(e)}
    return results
