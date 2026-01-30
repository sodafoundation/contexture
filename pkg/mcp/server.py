# mcp_server.py
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import pandas as pd
import yaml
import os

from fastmcp import FastMCP
from prometheus_api_client import PrometheusConnect
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi

app = FastMCP("Monitoring MCP Server")

prometheus_clients: Dict[str, PrometheusConnect] = {}

def load_config():
    
    config_dir = "../../config/"
    
    # Load Prometheus config
    prom_config_path = os.path.join(config_dir, "prometheus_config.yaml")
    prom_config = {}
    if os.path.exists(prom_config_path):
        with open(prom_config_path, 'r') as f:
            prom_config = yaml.safe_load(f)
    
    return prom_config

def initialize_clients():
    global prometheus_clients
    
    prom_config = load_config()
    
    for cfg in prom_config.get("prometheus_instances", []):
        name = cfg.get("name")
        try:
            prometheus_clients[name] = PrometheusConnect(
                url=cfg['base_url'],
                headers=cfg.get('headers', {}),
                disable_ssl=cfg.get('disable_ssl', False)
            )
            print(f"Initialized Prometheus client: {name} -> {cfg['base_url']}")
        except Exception as e:
            print(f"Failed to initialize Prometheus client {name}: {e}")

initialize_clients()


@app.tool()
def workload_metrics(
    metric_name: str = "container_cpu_usage_seconds_total",
    workload_name: Optional[str] = None,   
    pod_names: Optional[List[str]] = None,
    time_window: Optional[str] = None,     
    aggregation: str = "avg"               
) -> Dict[str, Any]:
    """
    Query workload-level gauge metrics from Prometheus.
    - Gauge metrics only
    - Aggregates across pods
    - Optional time window support
    """

    if not prometheus_clients:
        return {"error": "Prometheus client not initialized"}

    if not workload_name:
        return {"error": "workload_name (app label) must be provided"}

    if aggregation not in {"avg", "max", "min", "sum"}:
        return {"error": f"Invalid aggregation '{aggregation}'"}

    
    label_filters = [f'app="{workload_name}"']

    if pod_names:
        pod_regex = "|".join(pod_names)
        label_filters.append(f'pod=~"{pod_regex}"')

    label_selector = ",".join(label_filters)

    
    if time_window:
        inner_expr = f"{aggregation}_over_time({metric_name}{{{label_selector}}}[{time_window}])"
        query = f"{aggregation}({inner_expr})"
        effective_window = time_window
    else:
        query = f"{aggregation}({metric_name}{{{label_selector}}})"
        effective_window = "current"

    all_results = {}

    for prom_name, client in prometheus_clients.items():
        try:
            response = client.custom_query(query=query)

            value = None
            if response and len(response) > 0:
                try:
                    value = float(response[0]["value"][1])
                except (KeyError, ValueError, IndexError):
                    value = None

            all_results[prom_name] = {
                "query": query,
                "value": value
            }

        except Exception as e:
            return {"error": f"Failed to query Prometheus ({prom_name}): {str(e)}"}

    return {
        "metric": metric_name,
        "metric_type": "gauge",
        "workload": workload_name,
        "pods_filtered": pod_names or "ALL",
        "aggregation": aggregation,
        "time_window": effective_window,
        "results": all_results,
        "timestamp": datetime.now().isoformat()
    }

    
@app.tool()
def top_n_pods_by_metric(
    metric_name: str = "container_cpu_usage_seconds_total", 
    top_n: int = 5, 
    window: str = "30m"
) -> Dict[str, Any]:
    
    if not prometheus_clients:
        return {"error": "Prometheus client not initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        results = []
        try:
            # Filter metrics with a pod label
            query = f'topk({top_n}, avg_over_time({metric_name}{{pod!=""}}[{window}]))'
            result = client.custom_query(query=query)

            # Extract pod names and CPU usage values
            pods_info = []
            for item in result:
                metric = item.get("metric", {})
                pod_name = metric.get("pod")  # only include if pod exists
                value = float(item.get("value", [0, "0"])[1])
                if pod_name:
                    pods_info.append({"pod": pod_name, "value": value})

            # Sort by CPU usage descending
            pods_info.sort(key=lambda x: x["value"], reverse=True)

            

        except Exception as e:
            return {"error": str(e)}
        
        all_results[prom_name] = pods_info

    return {
            "pods_per_prometheus": all_results,
            "timestamp": datetime.now().isoformat()
        }

@app.tool()
def pod_network_io(pod_names: Optional[List[str]] = None) -> Dict[str, Any]:
    
    if not prometheus_clients:
        return {"error": "Prometheus client not initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        results = []
        try:
            results = []
            for pod_name in pod_names or []:
                rx_query = f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[5m])'
                tx_query = f'rate(container_network_transmit_bytes_total{{pod="{pod_name}"}}[5m])'
                rx_result = client.custom_query(rx_query)
                tx_result = client.custom_query(tx_query)
                rx = float(rx_result[0]['value'][1]) if rx_result else 0
                tx = float(tx_result[0]['value'][1]) if tx_result else 0
                results.append({"pod": pod_name, "rx_bytes_per_sec": rx, "tx_bytes_per_sec": tx})
            
        except Exception as e:
            return {"error": str(e)}
        all_results[prom_name] = results
    
    return {"pod_network_io_per_promotheus": all_results, "timestamp": datetime.now().isoformat()}

@app.tool()
def pods_exceeding_cpu(threshold: float = 0.8) -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = f'rate(container_cpu_usage_seconds_total[5m]) > {threshold}'
            result = client.custom_query(query=query)
            pods = [{"pod": item["metric"]["pod"], "cpu_value": float(item["value"][1])} 
                    for item in result if "pod" in item["metric"]]
            all_results[prom_name] = pods
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {
        "pods_exceeding_cpu_per_prometheus": all_results,
        "threshold": threshold,
        "timestamp": datetime.now().isoformat()
    }


@app.tool()
def pod_status_summary() -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = 'sum(kube_pod_status_phase) by (phase)'
            result = client.custom_query(query=query)
            status_summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            total = sum(status_summary.values())
            status_summary["total"] = total
            all_results[prom_name] = status_summary
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {
        "pod_status_summary_per_prometheus": all_results,
        "timestamp": datetime.now().isoformat()
    }

@app.tool()
def recent_pod_events(limit: int = 10) -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = 'sort_desc(sum by (reason, involved_object_name) (increase(kube_event_count[10m])))'
            result = client.custom_query(query=query)
            
            events = []
            for item in result[:limit]:
                metric = item.get("metric", {})
                events.append({
                    "pod": metric.get("involved_object_name"),
                    "reason": metric.get("reason"),
                    "count": int(float(item["value"][1]))
                })
            all_results[prom_name] = events
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {
        "recent_pod_events_per_prometheus": all_results,
        "lookback": "10m",
        "timestamp": datetime.now().isoformat()
    }


@app.tool()
def node_disk_usage(window_minutes: int = 20) -> Dict[str, Any]:
    """
    Summarized node disk usage (%) for important mount points across Prometheus clients.

    Args:
        window_minutes (int): Lookback window in minutes (default: 20).

    Returns:
        Dict[str, Any]: Aggregated disk usage per node.
    """

    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=window_minutes)
    step = "1m"  # 1-minute resolution

    important_mounts = {"/", "/var/lib", "/data"}
    all_results = {}

    for prom_name, client in prometheus_clients.items():
        try:
            query = """
            100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} 
                        / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))
            """

            result = client.custom_query_range(
                query=query.strip(),
                start_time=start_time,
                end_time=end_time,
                step=step
            )

            disk_usage = []
            for item in result:
                metric = item.get("metric", {})
                mount = metric.get("mountpoint", "")
                if mount not in important_mounts:
                    continue

                node = metric.get("node", "unknown")
                cluster = metric.get("cluster", "unknown")
                region = metric.get("region", "unknown")
                environment = metric.get("environment", "unknown")

                # Average usage across time range
                values = [float(v[1]) for v in item.get("values", [])]
                if not values:
                    continue
                avg_usage = sum(values) / len(values)

                disk_usage.append({
                    "node": node,
                    "mount": mount,
                    "cluster": cluster,
                    "region": region,
                    "environment": environment,
                    "avg_disk_usage_percent": round(avg_usage, 2),
                    "max_disk_usage_percent": round(max(values), 2),
                })

            disk_usage.sort(key=lambda x: x["max_disk_usage_percent"], reverse=True)

            all_results[prom_name] = {
                "query": query.strip(),
                "window_minutes": window_minutes,
                "timestamp": end_time.isoformat(),
                "top_nodes": disk_usage[:10],
            }

        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {
        "node_disk_usage_per_prometheus": all_results,
        "fetched_at": datetime.utcnow().isoformat(),
    }


@app.tool()
def describe_cluster_health() -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = 'sum(kube_pod_status_phase) by (phase)'
            result = client.custom_query(query=query)
            summary = {item["metric"]["phase"]: int(float(item["value"][1])) for item in result}
            total = sum(summary.values())
            running = summary.get("Running", 0)
            pending = summary.get("Pending", 0)
            failed = summary.get("Failed", 0)

            if failed > 0:
                status_msg = f"{failed} pods are failing. {running}/{total} pods are running."
            elif pending > 0:
                status_msg = f"{pending} pods are pending. {running}/{total} are running fine."
            else:
                status_msg = f"All systems nominal: {running}/{total} pods are healthy."

            all_results[prom_name] = {"summary": summary, "message": status_msg}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"cluster_health_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}


@app.tool()
def top_disk_pressure_nodes(threshold: float = 80.0, top_n: int = 5) -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = """
            100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} 
                        / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))
            """
            result = client.custom_query(query=query)
            nodes_info = []
            for item in result:
                metric = item.get("metric", {})
                node = metric.get("instance")
                mount = metric.get("mountpoint", "")
                usage = float(item.get("value", [0, "0"])[1])
                if usage >= threshold:
                    nodes_info.append({"node": node, "mount": mount, "usage_percent": round(usage, 2)})

            nodes_info.sort(key=lambda x: x["usage_percent"], reverse=True)
            nodes_info = nodes_info[:top_n]

            msg = f"⚠️ {len(nodes_info)} nodes above {threshold}% disk usage." if nodes_info else "✅ No nodes are under disk pressure."
            all_results[prom_name] = {"nodes": nodes_info, "message": msg, "threshold": threshold}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"top_disk_pressure_nodes_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}



@app.tool()
def pod_restart_trend(window: str = "30m", top_n: int = 5) -> Dict[str, Any]:
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = f'topk({top_n}, increase(kube_pod_container_status_restarts_total[{window}]))'
            result = client.custom_query(query=query)
            restart_trends = []
            for item in result:
                metric = item.get("metric", {})
                pod = metric.get("pod")
                container = metric.get("container", "")
                restarts = float(item.get("value", [0, "0"])[1])
                if pod:
                    restart_trends.append({"pod": pod, "container": container, "restarts": restarts})

            restart_trends.sort(key=lambda x: x["restarts"], reverse=True)
            msg = f"⚠️ Pods with recent restarts detected (last {window})." if restart_trends else f"✅ No recent restarts in the last {window}."
            all_results[prom_name] = {"pods": restart_trends, "message": msg, "window": window}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"pod_restart_trend_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}


@app.tool()
def detect_pod_anomalies(metric_name="container_cpu_usage_seconds_total", z_threshold=3.0):
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = f'avg_over_time({metric_name}{{pod!=""}}[15m])'
            result = client.custom_query(query=query)
            values = [float(r["value"][1]) for r in result]
            if not values:
                all_results[prom_name] = {"message": "No data"}
                continue

            mean = sum(values)/len(values)
            std = (sum((x-mean)**2 for x in values)/len(values))**0.5
            anomalies = []
            for r in result:
                pod = r["metric"].get("pod")
                val = float(r["value"][1])
                z = (val - mean)/std if std > 0 else 0
                if abs(z) > z_threshold:
                    anomalies.append({"pod": pod, "value": val, "z_score": round(z,2)})

            all_results[prom_name] = {"anomalies": anomalies, "mean": mean, "std": std}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"pod_anomalies_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}


@app.tool()
def namespace_resource_summary(resource="cpu", window="5m"):
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    metric = "container_cpu_usage_seconds_total" if resource=="cpu" else "container_memory_usage_bytes"

    for prom_name, client in prometheus_clients.items():
        try:
            query = f'sum(rate({metric}{{namespace!=""}}[{window}])) by (namespace)'
            result = client.custom_query(query=query)
            usage = [{"namespace": r["metric"]["namespace"], "value": float(r["value"][1])} for r in result]
            total = sum(x["value"] for x in usage)
            for x in usage:
                x["percent_of_total"] = round((x["value"]/total)*100, 2) if total > 0 else 0
            usage.sort(key=lambda x: x["value"], reverse=True)
            all_results[prom_name] = {"resource": resource, "usage_by_namespace": usage}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"namespace_resource_summary_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}



@app.tool()
def detect_crashloop_pods(window="10m", threshold=2):
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = f'increase(kube_pod_container_status_restarts_total[{window}]) > {threshold}'
            result = client.custom_query(query=query)
            pods = [{"pod": r["metric"]["pod"], "restarts": int(float(r["value"][1]))} for r in result if "pod" in r["metric"]]
            all_results[prom_name] = {"crashloop_pods": pods, "window": window}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"crashloop_pods_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}


@app.tool()
def correlate_metrics(metric_a="container_cpu_usage_seconds_total", metric_b="container_network_receive_bytes_total", window="10m"):
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    import numpy as np
    all_results = {}

    for prom_name, client in prometheus_clients.items():
        try:
            r1 = client.custom_query(f'rate({metric_a}[{window}])')
            r2 = client.custom_query(f'rate({metric_b}[{window}])')
            data_a = {r["metric"].get("pod"): float(r["value"][1]) for r in r1 if "pod" in r["metric"]}
            data_b = {r["metric"].get("pod"): float(r["value"][1]) for r in r2 if "pod" in r["metric"]}
            common_pods = set(data_a) & set(data_b)
            if not common_pods:
                all_results[prom_name] = {"message": "No overlapping pods"}
                continue
            pairs = [(data_a[p], data_b[p]) for p in common_pods]
            corr = float(np.corrcoef([x for x, _ in pairs], [y for _, y in pairs])[0,1])
            all_results[prom_name] = {"correlation": round(corr, 3), "metric_a": metric_a, "metric_b": metric_b, "window": window}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"correlation_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}



@app.tool()
def pod_event_timeline(pod_name: str, window: str = "30m"):
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    queries = {
        "restarts": f'increase(kube_pod_container_status_restarts_total{{pod="{pod_name}"}}[{window}])',
        "network_rx": f'rate(container_network_receive_bytes_total{{pod="{pod_name}"}}[{window}])',
        "cpu": f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}"}}[{window}])',
    }

    for prom_name, client in prometheus_clients.items():
        try:
            timeline = {}
            for key, q in queries.items():
                result = client.custom_query(q)
                if result:
                    timeline[key] = float(result[0]["value"][1])
            all_results[prom_name] = {"pod": pod_name, "timeline": timeline, "window": window}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"pod_event_timeline_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}



@app.tool()
def node_condition_summary():
    if not prometheus_clients:
        return {"error": "No Prometheus clients initialized"}

    all_results = {}
    for prom_name, client in prometheus_clients.items():
        try:
            query = 'kube_node_status_condition{status="true", condition!="Ready"}'
            result = client.custom_query(query=query)
            issues = [{"node": r["metric"]["node"], "condition": r["metric"]["condition"]} for r in result]
            all_results[prom_name] = {"node_issues": issues}
        except Exception as e:
            all_results[prom_name] = {"error": str(e)}

    return {"node_condition_summary_per_prometheus": all_results, "timestamp": datetime.now().isoformat()}



if __name__ == "__main__":
    app.run()
