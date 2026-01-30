#!/usr/bin/env python3
"""
Prometheus High-Cardinality Data Generator for Kubernetes Clusters
This script generates and pushes high-cardinality time-series data to Prometheus
simulating multiple Kubernetes clusters with one year of historical data.
"""

import json
import random
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import argparse
import sys

try:
    from prometheus_remote_writer import RemoteWriter
except ImportError:
    print("Error: prometheus-remote-writer not installed. Install it using:")
    print("pip install prometheus-remote-writer")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration class for Prometheus connection and data generation"""
    def __init__(self, config_file: str = None, prometheus_url: str = None):
        if config_file:
            with open(config_file, 'r') as f:
                config = json.load(f)
                self.prometheus_url = config.get('prometheus_url')
                self.auth_token = config.get('auth_token')
                self.num_clusters = config.get('num_clusters', 10)
                self.nodes_per_cluster = config.get('nodes_per_cluster', 50)
                self.namespaces_per_cluster = config.get('namespaces_per_cluster', 20)
                self.pods_per_namespace = config.get('pods_per_namespace', 30)
                self.containers_per_pod = config.get('containers_per_pod', 3)
                self.scrape_interval = config.get('scrape_interval', 30)
                self.batch_size = config.get('batch_size', 1000)
                self.days_of_history = config.get('days_of_history', 365)
                self.services = ['frontend', 'backend', 'payments', 'cache', 'auth', 'api']
        else:
            self.prometheus_url = prometheus_url or "http://localhost:9090/api/v1/write"
            self.auth_token = None
            self.num_clusters = 10
            self.nodes_per_cluster = 50
            self.namespaces_per_cluster = 20
            self.pods_per_namespace = 30
            self.containers_per_pod = 3
            self.scrape_interval = 30  # seconds
            self.batch_size = 1000
            self.days_of_history = 365


class KubernetesMetricsGenerator:
    """Generate realistic Kubernetes metrics with high cardinality"""

    def __init__(self, config: Config):
        self.config = config
        self.clusters = self._generate_cluster_names()
        self.regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-south-1', 'ap-southeast-1']
        self.environments = ['production', 'staging', 'development', 'qa']
        self.namespaces = ['default', 'kube-system', 'monitoring', 'logging', 'istio-system',
                          'ingress-nginx', 'cert-manager', 'mysql', 'redis', 'kafka',
                          'app-backend', 'app-frontend', 'app-api', 'app-worker', 'app-scheduler']
        self.container_names = ['app', 'sidecar', 'init', 'proxy', 'metrics-exporter',
                               'log-collector', 'cache', 'database', 'queue', 'worker']
        self.services = ['app', 'sidecar', 'init', 'proxy', 'metrics-exporter',
                               'log-collector', 'cache', 'database', 'queue', 'worker']

    def _generate_cluster_names(self) -> List[str]:
        """Generate cluster names"""
        return [f"k8s-cluster-{i:03d}" for i in range(1, self.config.num_clusters + 1)]
    
    def generate_istio_metrics(self, timestamp: int, source_service: str, dest_service: str, labels: Dict[str, str]):
        """Simulate Istio request metrics between services"""
        metrics = []

        # Total requests
        total_requests = random.randint(0, 200)
        metrics.append({
            'metric': {**labels, '__name__': 'istio_requests_total',
                    'source_workload': source_service,
                    'destination_workload': dest_service},
            'values': [float(total_requests)],
            'timestamps': [timestamp]
        })

        # Error requests
        error_requests = random.randint(0, 5)
        metrics.append({
            'metric': {**labels, '__name__': 'istio_requests_error_total',
                    'source_workload': source_service,
                    'destination_workload': dest_service},
            'values': [float(error_requests)],
            'timestamps': [timestamp]
        })

        # Latency histogram (simplified as avg)
        latency = random.uniform(0.01, 0.5)  # seconds
        metrics.append({
            'metric': {**labels, '__name__': 'istio_request_duration_seconds',
                    'source_workload': source_service,
                    'destination_workload': dest_service},
            'values': [latency],
            'timestamps': [timestamp]
        })

        return metrics


    def _generate_node_name(self, cluster: str, node_id: int) -> str:
        """Generate node name"""
        return f"{cluster}-node-{node_id:04d}"

    def _generate_pod_name(self, namespace: str, pod_id: int) -> str:
        """Generate pod name"""
        app_name = random.choice(['nginx', 'api', 'worker', 'cache', 'db', 'frontend', 'backend'])
        return f"{app_name}-{random.randint(100000, 999999)}-{pod_id}"

    def generate_cpu_metrics(self, timestamp: int, labels: Dict[str, str]) -> List[Dict]:
        """Generate CPU usage metrics"""
        metrics = []

        # CPU usage percentage (0-100)
        cpu_usage = random.uniform(5, 95)
        metrics.append({
            'metric': {**labels, '__name__': 'container_cpu_usage_seconds_total'},
            'values': [cpu_usage],
            'timestamps': [timestamp]
        })

        # CPU throttling
        throttle_count = random.randint(0, 1000)
        metrics.append({
            'metric': {**labels, '__name__': 'container_cpu_cfs_throttled_seconds_total'},
            'values': [float(throttle_count)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_node_filesystem_metrics(self, timestamp: int, node_labels: Dict[str, str]) -> List[Dict]:
        """Generate fake node filesystem metrics for disk usage queries"""
        metrics = []
        mountpoints = ["/", "/var/lib", "/data"]

        for mount in mountpoints:
            total_bytes = random.randint(50, 500) * 1024 * 1024 * 1024  # 50–500 GB
            used_ratio = random.uniform(0.3, 0.9)
            avail_bytes = int(total_bytes * (1 - used_ratio))

            metrics.append({
                "metric": {
                    **node_labels,
                    "__name__": "node_filesystem_size_bytes",
                    "mountpoint": mount,
                    "fstype": random.choice(["ext4", "xfs"]),
                },
                "values": [float(total_bytes)],
                "timestamps": [timestamp],
            })

            metrics.append({
                "metric": {
                    **node_labels,
                    "__name__": "node_filesystem_avail_bytes",
                    "mountpoint": mount,
                    "fstype": random.choice(["ext4", "xfs"]),
                },
                "values": [float(avail_bytes)],
                "timestamps": [timestamp],
            })

        return metrics


    def generate_memory_metrics(self, timestamp: int, labels: Dict[str, str]) -> List[Dict]:
        """Generate memory metrics"""
        metrics = []

        # Memory usage in bytes
        memory_usage = random.randint(100 * 1024 * 1024, 8 * 1024 * 1024 * 1024)  # 100MB to 8GB
        metrics.append({
            'metric': {**labels, '__name__': 'container_memory_usage_bytes'},
            'values': [float(memory_usage)],
            'timestamps': [timestamp]
        })

        # Memory working set
        working_set = int(memory_usage * random.uniform(0.6, 0.9))
        metrics.append({
            'metric': {**labels, '__name__': 'container_memory_working_set_bytes'},
            'values': [float(working_set)],
            'timestamps': [timestamp]
        })

        # Memory cache
        cache = int(memory_usage * random.uniform(0.1, 0.3))
        metrics.append({
            'metric': {**labels, '__name__': 'container_memory_cache'},
            'values': [float(cache)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_network_metrics(self, timestamp: int, labels: Dict[str, str]) -> List[Dict]:
        """Generate network metrics"""
        metrics = []

        # Network receive bytes
        rx_bytes = random.randint(1000000, 1000000000)  # 1MB to 1GB
        metrics.append({
            'metric': {**labels, '__name__': 'container_network_receive_bytes_total'},
            'values': [float(rx_bytes)],
            'timestamps': [timestamp]
        })

        # Network transmit bytes
        tx_bytes = random.randint(1000000, 1000000000)
        metrics.append({
            'metric': {**labels, '__name__': 'container_network_transmit_bytes_total'},
            'values': [float(tx_bytes)],
            'timestamps': [timestamp]
        })

        # Network errors
        rx_errors = random.randint(0, 100)
        metrics.append({
            'metric': {**labels, '__name__': 'container_network_receive_errors_total'},
            'values': [float(rx_errors)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_disk_metrics(self, timestamp: int, labels: Dict[str, str]) -> List[Dict]:
        """Generate disk I/O metrics"""
        metrics = []

        # Disk read bytes
        read_bytes = random.randint(1000000, 500000000)
        metrics.append({
            'metric': {**labels, '__name__': 'container_fs_reads_bytes_total'},
            'values': [float(read_bytes)],
            'timestamps': [timestamp]
        })

        # Disk write bytes
        write_bytes = random.randint(1000000, 500000000)
        metrics.append({
            'metric': {**labels, '__name__': 'container_fs_writes_bytes_total'},
            'values': [float(write_bytes)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_pod_metrics(self, timestamp: int, labels: Dict[str, str]) -> List[Dict]:
        """Generate pod-level metrics"""
        metrics = []

        phase_mapping = {
        0: "Pending",
        1: "Running",
        2: "Succeeded",
        3: "Failed"
        }

        # Pod status (0=Pending, 1=Running, 2=Succeeded, 3=Failed)
        pod_status = random.choice([1, 1, 1, 1, 1, 0, 2])  # Mostly running
        phase_label = phase_mapping[pod_status]
        metrics.append({
            'metric': {**labels, '__name__': 'kube_pod_status_phase', "phase":phase_label},
            'values': [float(pod_status)],
            'timestamps': [timestamp]
        })

        # Container restarts
        restarts = random.randint(0, 10)
        metrics.append({
            'metric': {**labels, '__name__': 'kube_pod_container_status_restarts_total'},
            'values': [float(restarts)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_node_metrics(self, timestamp: int, node_labels: Dict[str, str]) -> List[Dict]:
        """Generate node-level metrics"""
        metrics = []

        # Node CPU capacity
        cpu_capacity = random.choice([4, 8, 16, 32, 64])
        metrics.append({
            'metric': {**node_labels, '__name__': 'kube_node_status_capacity_cpu_cores'},
            'values': [float(cpu_capacity)],
            'timestamps': [timestamp]
        })

        # Node memory capacity (in bytes)
        memory_capacity = cpu_capacity * 4 * 1024 * 1024 * 1024  # 4GB per core
        metrics.append({
            'metric': {**node_labels, '__name__': 'kube_node_status_capacity_memory_bytes'},
            'values': [float(memory_capacity)],
            'timestamps': [timestamp]
        })

        # Node condition (1=Ready, 0=NotReady)
        node_ready = random.choices([1, 0], weights=[0.99, 0.01])[0]
        metrics.append({
            'metric': {**node_labels, '__name__': 'kube_node_status_condition', 'condition': 'Ready'},
            'values': [float(node_ready)],
            'timestamps': [timestamp]
        })

        return metrics

    def generate_all_metrics(self, timestamp: int) -> List[Dict]:
        """Generate all metrics for all clusters, nodes, pods, and containers"""
        all_metrics = []

        for cluster in self.clusters:
            region = random.choice(self.regions)
            environment = random.choice(self.environments)

            # Generate node metrics
            for node_id in range(1, min(self.config.nodes_per_cluster + 1, 11)):  # Limit for initial testing
                node_name = self._generate_node_name(cluster, node_id)
                node_labels = {
                    'cluster': cluster,
                    'node': node_name,
                    'region': region,
                    'environment': environment,
                    'instance_type': random.choice(['t3.large', 't3.xlarge', 'm5.large', 'm5.xlarge', 'c5.2xlarge'])
                }
                all_metrics.extend(self.generate_node_metrics(timestamp, node_labels))

            # Generate pod and container metrics
            for namespace in self.namespaces[:min(self.config.namespaces_per_cluster, 5)]:  # Limit for initial testing
                for pod_id in range(1, min(self.config.pods_per_namespace + 1, 6)):  # Limit for initial testing
                    pod_name = self._generate_pod_name(namespace, pod_id)
                    node_name = self._generate_node_name(cluster, random.randint(1, min(self.config.nodes_per_cluster, 10)))

                    for container_id in range(1, min(self.config.containers_per_pod + 1, 3)):
                        container_name = random.choice(self.container_names)

                        labels = {
                            'cluster': cluster,
                            'namespace': namespace,
                            'pod': pod_name,
                            'container': f"{container_name}-{container_id}",
                            'node': node_name,
                            'region': region,
                            'environment': environment,
                            'app': pod_name.split('-')[0],
                            'version': f"v{random.randint(1, 5)}.{random.randint(0, 10)}.{random.randint(0, 20)}"
                        }

                        all_metrics.extend(self.generate_cpu_metrics(timestamp, labels))
                        all_metrics.extend(self.generate_memory_metrics(timestamp, labels))
                        all_metrics.extend(self.generate_network_metrics(timestamp, labels))
                        all_metrics.extend(self.generate_disk_metrics(timestamp, labels))
                        all_metrics.extend(self.generate_pod_metrics(timestamp, labels))
                        all_metrics.extend(self.generate_node_filesystem_metrics(timestamp, node_labels))

        for source in self.services:
            dest = random.choice([s for s in self.services if s != source])
            all_metrics.extend(self.generate_istio_metrics(timestamp, source, dest, labels))
        
        return all_metrics


class PrometheusDataPusher:
    """Push metrics data to Prometheus using Remote Write API"""

    def __init__(self, config: Config):
        self.config = config
        headers = {}
        if config.auth_token:
            headers['Authorization'] = f'Bearer {config.auth_token}'

        self.writer = RemoteWriter(
            url=config.prometheus_url,
            headers=headers if headers else None,
            timeout=30
        )
        self.metrics_generator = KubernetesMetricsGenerator(config)

    def push_historical_data(self):
        """Generate and push historical data for the specified time range"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=self.config.days_of_history)

        logger.info(f"Starting to push historical data from {start_time} to {end_time}")
        logger.info(f"Clusters: {self.config.num_clusters}")
        logger.info(f"Scrape interval: {self.config.scrape_interval} seconds")

        total_intervals = int((end_time - start_time).total_seconds() / self.config.scrape_interval)
        logger.info(f"Total time intervals to process: {total_intervals}")

        batch = []
        batch_count = 0
        total_metrics_sent = 0

        current_time = start_time
        interval_count = 0

        while current_time <= end_time:
            timestamp_ms = int(current_time.timestamp() * 1000)

            # Generate metrics for this timestamp
            metrics = self.metrics_generator.generate_all_metrics(timestamp_ms)
            batch.extend(metrics)

            # Send batch when it reaches the batch size
            if len(batch) >= self.config.batch_size:
                try:
                    self.writer.send(batch)
                    total_metrics_sent += len(batch)
                    batch_count += 1
                    logger.info(f"Sent batch {batch_count} with {len(batch)} metrics. "
                              f"Total metrics sent: {total_metrics_sent}. "
                              f"Progress: {interval_count}/{total_intervals} intervals "
                              f"({(interval_count/total_intervals)*100:.2f}%)")
                    batch = []
                except Exception as e:
                    logger.error(f"Error sending batch: {e}")
                    # Optional: implement retry logic here
                    batch = []

            # Move to next interval
            current_time += timedelta(seconds=self.config.scrape_interval)
            interval_count += 1

            # Small sleep to avoid overwhelming the system
            if interval_count % 10 == 0:
                time.sleep(0.1)

        # Send remaining metrics
        if batch:
            try:
                self.writer.send(batch)
                total_metrics_sent += len(batch)
                logger.info(f"Sent final batch with {len(batch)} metrics")
            except Exception as e:
                logger.error(f"Error sending final batch: {e}")

        logger.info(f"Completed! Total metrics sent: {total_metrics_sent} in {batch_count} batches")

        # Calculate estimated cardinality
        estimated_cardinality = (
            self.config.num_clusters *
            self.config.nodes_per_cluster *
            self.config.namespaces_per_cluster *
            self.config.pods_per_namespace *
            self.config.containers_per_pod *
            15  # Average number of unique metric types per container
        )
        logger.info(f"Estimated total time series cardinality: ~{estimated_cardinality:,}")


def main():
    parser = argparse.ArgumentParser(
        description='Push high-cardinality Kubernetes metrics to Prometheus'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to JSON configuration file'
    )
    parser.add_argument(
        '--url',
        type=str,
        help='Prometheus remote write URL (e.g., http://localhost:9090/api/v1/write)'
    )
    parser.add_argument(
        '--clusters',
        type=int,
        default=10,
        help='Number of Kubernetes clusters to simulate (default: 10)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=365,
        help='Number of days of historical data (default: 365)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Number of metrics per batch (default: 1000)'
    )
    parser.add_argument(
        '--scrape-interval',
        type=int,
        default=30,
        help='Scrape interval in seconds (default: 30)'
    )

    args = parser.parse_args()

    # Load configuration
    if args.config:
        config = Config(config_file=args.config)
    elif args.url:
        config = Config(prometheus_url=args.url)
        config.num_clusters = args.clusters
        config.days_of_history = args.days
        config.batch_size = args.batch_size
        config.scrape_interval = args.scrape_interval
    else:
        logger.error("Either --config or --url must be provided")
        parser.print_help()
        sys.exit(1)

    # Create pusher and start pushing data
    pusher = PrometheusDataPusher(config)

    try:
        pusher.push_historical_data()
    except KeyboardInterrupt:
        logger.info("\\nInterrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()