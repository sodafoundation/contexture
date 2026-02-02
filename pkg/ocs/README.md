# Contexture OCS Service

<div align="center">
  <img src="https://www.loginradius.com/assets/blog/engineering/istio-service-mesh/Istio.webp" alt="Istio" height="80" style="margin: 0 15px;">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/3/38/Prometheus_software_logo.svg/1280px-Prometheus_software_logo.svg.png" alt="Prometheus" height="80" style="margin: 0 15px;">
  <img src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRtovlsBMk0rvY-OWj2EzOc0yLnIRZWY4Pedw&s" alt="Prometheus" height="80" style="margin: 0 15px;">
</div>

A Go-based service that collects service mesh metrics from Prometheus, builds workload topology, and provides context definitions for observability analysis

## Overview

The OCS Server provides:
- **Istio Metrics Collection**: Queries Prometheus for `istio_requests_total` metrics filtered by source workloads
- **Topology Building**: Extracts source-destination workload relationships and stores them as adjacency lists in MongoDB
- **Context Definitions**: Provides structured context information combining topology, metrics, and policies for observability analysis

## Prerequisites

- Go 1.21 or higher
- MongoDB (running locally or accessible via `MONGODB_URI`)
- Prometheus (with Istio metrics exposed)
- Access to Prometheus API endpoint

## Installation

1. **Install dependencies**:
```bash
go mod tidy
```

2. **Configure MongoDB** (optional, defaults to `mongodb://localhost:27017/`):
```bash
export MONGODB_URI="mongodb://localhost:27017/"
export MONGODB_DB_NAME="ocs"
```

3. **Configure server port** (optional, defaults to 8000):
```bash
export PORT="8000"
```

4. **Ensure Prometheus is configured** in `config/prometheus_config.yaml`

5. **Configure OCS settings** in `pkg/ocs/ocs_config.yaml`

## Configuration

### OCS Config (`ocs_config.yaml`)

```yaml
policy:
  - "sla violation if cpu utilization is greater than 90%"

metrics:
  - name: "cpu_utilization"
    type: "gauge"
    unit: "percentage"
    description: "Current CPU usage against pod limits"
    aggregation_logic: "average"
    health_config:
      critical_threshold: 90
      polarity: "high_is_bad"

workload:
  - database
  - cache
  - app
  - proxy

time_window_minutes: 5  # Optional: auto time window for queries
```

### Prometheus Config (`config/prometheus_config.yaml`)

```yaml
prometheus_instances:
  - name: prometheus_1
    base_url: "http://localhost:9090"
    headers: {}
    disable_ssl: false
```

## Running the Server

### Development Mode

```bash
# Run all files in the package
go run ./pkg/ocs/

# Or specify all files explicitly
go run pkg/ocs/*.go
```

### Production Mode

```bash
# Build the binary
go build -o ocs-server ./pkg/ocs/

# Run the binary
./ocs-server
```

## API Endpoints

### GET `/get_ocs_prompt`

Returns OCS context definitions combining topology from MongoDB, metrics, and policies from config.

**Response:**
```json
{
  "spec_version": "0.1",
  "context_definitions": [
    {
      "resource_id": "workload-database",
      "domain": "compute.k8s",
      "identity": {
        "workload": "database"
      },
      "metrics": [...],
      "topology": {
        "dependencies": ["cache", "app"],
        "dependents": ["proxy"]
      },
      "policy": ["sla violation if cpu utilization is greater than 90%"]
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:8000/get_ocs_prompt
```

### POST `/collect_istio_metrics`

Queries Prometheus for Istio request metrics, extracts workload topology, and saves to MongoDB.

**Query Parameters (optional):**
- `from_timestamp`: Start time (RFC3339 or Unix timestamp)
- `to_timestamp`: End time (RFC3339 or Unix timestamp)

If timestamps are not provided and `time_window_minutes` is configured, uses automatic time window.

**Response:**
```json
{
  "status": "success",
  "message": "Metrics collected and saved to MongoDB",
  "adjacency_list": {
    "database": ["cache", "app"],
    "app": ["database"]
  },
  "document_id": "507f1f77bcf86cd799439011",
  "timestamp": "2024-01-01T00:00:00Z",
  "from_timestamp": "2024-01-01T00:00:00Z",
  "to_timestamp": "2024-01-01T00:05:00Z",
  "time_window_minutes": 5
}
```

**Examples:**
```bash
# Use configured time window (5 minutes)
curl -X POST http://localhost:8000/collect_istio_metrics

# Use custom time range
curl -X POST "http://localhost:8000/collect_istio_metrics?from_timestamp=2024-01-01T00:00:00Z&to_timestamp=2024-01-01T23:59:59Z"

# Use Unix timestamps
curl -X POST "http://localhost:8000/collect_istio_metrics?from_timestamp=1704067200&to_timestamp=1704153600"
```

### GET `/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "prometheus": true,
  "mongodb": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Example:**
```bash
curl http://localhost:8000/health
```

## MongoDB Schema

The adjacency list is stored in the `workload_adjacency` collection:

```json
{
  "_id": ObjectId("..."),
  "adjacency_list": {
    "source_workload": ["destination1", "destination2"]
  },
  "timestamp": ISODate("..."),
  "source_count": 2,
  "total_connections": 3
}
```

## Troubleshooting

### "MongoDB not initialized" error
- Check MongoDB is running
- Verify `MONGODB_URI` environment variable
- Check connection string format

### "Prometheus query failed" error
- Verify Prometheus is accessible at configured URL
- Check network connectivity
- Verify Istio metrics are being scraped

### "No source workloads configured" error
- Ensure `workload` list is populated in `ocs_config.yaml`
- Check YAML syntax is correct

## License

See LICENSE file in project root.

