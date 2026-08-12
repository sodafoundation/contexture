package prompt

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	connectors "github.com/contexture/ocs/pkg/ocs/topology"
)

func TestBuildContextDefinitions(t *testing.T) {
	// 1. Mock Server to simulate Prometheus endpoints
	var mockMetadata map[string]interface{}
	var mockTargets map[string]interface{}
	var mockBuildInfo map[string]interface{}
	var mockRules map[string]interface{}
	var mockRuntimeInfo map[string]interface{}
	var mockMetricNames map[string]interface{}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if strings.Contains(r.URL.Path, "/api/v1/query") && strings.Contains(r.URL.RawQuery, "prometheus_build_info") {
			json.NewEncoder(w).Encode(mockBuildInfo)
			return
		}
		if strings.Contains(r.URL.Path, "/api/v1/metadata") {
			json.NewEncoder(w).Encode(mockMetadata)
			return
		}
		if strings.Contains(r.URL.Path, "/api/v1/targets") {
			json.NewEncoder(w).Encode(mockTargets)
			return
		}
		if strings.Contains(r.URL.Path, "/api/v1/rules") {
			json.NewEncoder(w).Encode(mockRules)
			return
		}
		if strings.Contains(r.URL.Path, "/api/v1/status/runtimeinfo") {
			json.NewEncoder(w).Encode(mockRuntimeInfo)
			return
		}
		if strings.Contains(r.URL.Path, "/api/v1/label/__name__/values") {
			json.NewEncoder(w).Encode(mockMetricNames)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	// Setup realistic responses
	mockBuildInfo = map[string]interface{}{
		"status": "success",
		"data": map[string]interface{}{
			"resultType": "vector",
			"result": []interface{}{
				map[string]interface{}{
					"metric": map[string]string{
						"version": "3.13.1",
					},
				},
			},
		},
	}

	mockMetricNames = map[string]interface{}{
		"status": "success",
		"data":   []string{"up"},
	}

	mockMetadata = map[string]interface{}{
		"status": "success",
		"data": map[string]interface{}{
			"up": []interface{}{
				map[string]string{
					"type": "gauge",
					"help": "Scrape target health status.",
					"unit": "boolean",
				},
			},
		},
	}

	mockTargets = map[string]interface{}{
		"status": "success",
		"data": map[string]interface{}{
			"activeTargets": []interface{}{
				map[string]interface{}{
					"scrapeUrl": "http://127.0.0.1:9100/metrics",
					"health":    "up",
					"labels": map[string]string{
						"job": "node-exporter",
					},
				},
			},
		},
	}

	mockRules = map[string]interface{}{
		"status": "success",
		"data": map[string]interface{}{
			"groups": []interface{}{
				map[string]interface{}{
					"name": "alerts",
					"rules": []interface{}{
						map[string]interface{}{
							"name":  "InstanceDown",
							"query": "up == 0",
						},
					},
				},
			},
		},
	}

	mockRuntimeInfo = map[string]interface{}{
		"status": "success",
		"data": map[string]interface{}{
			"storageRetention": "15d",
		},
	}

	discoverer := NewPrometheusDiscoverer(server.URL)
	cfg := &config.OCSConfig{
		IdentityAndOrigin: config.IdentityAndOriginConfig{
			ProviderSource:  "Prometheus",
			Environment:     "production",
			NamespaceDomain: "default",
		},
		DimensionalityAndTopology: config.TopologyConfig{
			ResourceType: "kubernetes_cluster",
			LabelsTags: map[string]string{
				"env": "prod",
			},
		},
		Metrics: []config.MetricConfigV2{
			{
				Name: "up",
				Semantics: config.MetricSemanticsConfig{
					DescriptiveName: "Target Health Status",
					Unit:            "boolean",
					Type:            "gauge",
					Description:     "Determines health status.",
				},
				Constraints: config.MetricConstraintsConfig{
					Thresholds: map[string]float64{
						"warning": 1.0,
					},
					Polarity: "low_is_bad",
				},
			},
		},
		Workload: []string{"frontend"},
	}

	adjacencyList := make(connectors.AdjacencyList)
	adjacencyList["frontend"] = []string{"backend"}

	// 2. Perform verification with mock discoverer
	ctx := context.Background()
	contextDefs := BuildContextDefinitions(ctx, adjacencyList, cfg, discoverer)

	if len(contextDefs) == 0 {
		t.Fatalf("Expected at least one context definition, got 0")
	}

	def := contextDefs[0]

	// Verify identity
	if def.IdentityAndOrigin.Who["binary_version"] != "3.13.1" {
		t.Errorf("Expected binary version 3.13.1, got %v", def.IdentityAndOrigin.Who["binary_version"])
	}

	// Verify metrics
	if len(def.MetricSemantics) == 0 || def.MetricSemantics[0].Name != "up" {
		t.Errorf("Expected metric 'up' in semantics, got empty or wrong metric name")
	}

	// Verify provenance
	provenanceMap := def.ProvenanceMap
	if provenanceMap == nil {
		t.Fatalf("Expected non-nil provenance_map")
	}

	verProv, ok := provenanceMap["identity.version"]
	if !ok || verProv.Provenance != "observed" || verProv.Value != "3.13.1" {
		t.Errorf("Expected observed provenance for identity version, got: %+v", verProv)
	}

	metricProv, ok := provenanceMap["metrics.up.type"]
	if !ok || metricProv.Provenance != "observed" || metricProv.Value != "gauge" {
		t.Errorf("Expected observed provenance for metrics.up.type, got: %+v", metricProv)
	}
}

func TestPartialFailureGracefulHandling(t *testing.T) {
	// Simulate server failing to return data for version/metadata (HTTP 500)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	discoverer := NewPrometheusDiscoverer(server.URL)
	cfg := &config.OCSConfig{
		IdentityAndOrigin: config.IdentityAndOriginConfig{
			ProviderSource:  "Prometheus",
			Environment:     "production",
			NamespaceDomain: "default",
		},
		Metrics: []config.MetricConfigV2{
			{
				Name: "up",
				Semantics: config.MetricSemanticsConfig{
					DescriptiveName: "Target Health Status",
					Unit:            "boolean",
					Type:            "gauge",
				},
			},
		},
		Workload: []string{"frontend"},
	}

	adjacencyList := make(connectors.AdjacencyList)

	ctx := context.Background()
	contextDefs := BuildContextDefinitions(ctx, adjacencyList, cfg, discoverer)

	if len(contextDefs) == 0 {
		t.Fatalf("Expected at least one context definition despite backend failures")
	}

	def := contextDefs[0]

	// Version should fallback to unknown rather than crashing
	if def.IdentityAndOrigin.Who["binary_version"] != "unknown" {
		t.Errorf("Expected binary version fallback to 'unknown', got %v", def.IdentityAndOrigin.Who["binary_version"])
	}

	// Provenance map should denote unknown/configured state
	provenanceMap := def.ProvenanceMap
	if val, ok := provenanceMap["identity.version"]; !ok || val.Provenance != "unknown" {
		t.Errorf("Expected identity.version to have 'unknown' provenance, got %+v", val)
	}
}
