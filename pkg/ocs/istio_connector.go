package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// IstioConnector handles Istio metrics queries via Prometheus
type IstioConnector struct {
	prometheusURL string
	httpClient    *http.Client
}

// NewIstioConnector creates a new Istio connector
func NewIstioConnector(prometheusURL string) *IstioConnector {
	return &IstioConnector{
		prometheusURL: prometheusURL,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// QueryMetrics queries Prometheus for istio_requests_total filtered by source workload
// If fromTimestamp and toTimestamp are provided, uses range query, otherwise uses instant query
func (ic *IstioConnector) QueryMetrics(sourceWorkloads []string, fromTimestamp, toTimestamp *time.Time) (*PrometheusQueryResult, error) {
	if len(sourceWorkloads) == 0 {
		return nil, fmt.Errorf("no source workloads provided")
	}

	// Build PromQL query with source workload filter
	workloadFilter := strings.Join(sourceWorkloads, "|")
	query := fmt.Sprintf(`istio_requests_total{source_workload=~"%s"}`, workloadFilter)

	if fromTimestamp != nil && toTimestamp != nil {
		return ic.queryRange(query, fromTimestamp, toTimestamp)
	}
	return ic.queryInstant(query)
}

// queryRange executes a Prometheus range query
func (ic *IstioConnector) queryRange(query string, fromTimestamp, toTimestamp *time.Time) (*PrometheusQueryResult, error) {
	start := fromTimestamp.Unix()
	end := toTimestamp.Unix()
	step := "15s" // Default step, can be made configurable

	queryURL := fmt.Sprintf("%s/api/v1/query_range?query=%s&start=%d&end=%d&step=%s",
		ic.prometheusURL, url.QueryEscape(query), start, end, step)
	log.Printf("Querying Prometheus (range): %s from %s to %s", query, fromTimestamp.Format(time.RFC3339), toTimestamp.Format(time.RFC3339))

	req, err := http.NewRequest("GET", queryURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := ic.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Prometheus returned status %d: %s", resp.StatusCode, string(body))
	}

	var rangeResult PrometheusQueryRangeResult
	if err := json.NewDecoder(resp.Body).Decode(&rangeResult); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if rangeResult.Status != "success" {
		return nil, fmt.Errorf("Prometheus query failed with status: %s", rangeResult.Status)
	}

	// Convert range result to instant query result format
	return ic.convertRangeToInstantResult(&rangeResult), nil
}

// queryInstant executes a Prometheus instant query
func (ic *IstioConnector) queryInstant(query string) (*PrometheusQueryResult, error) {
	queryURL := fmt.Sprintf("%s/api/v1/query?query=%s", ic.prometheusURL, url.QueryEscape(query))
	log.Printf("Querying Prometheus (instant): %s", query)

	req, err := http.NewRequest("GET", queryURL, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := ic.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("Prometheus returned status %d: %s", resp.StatusCode, string(body))
	}

	var result PrometheusQueryResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	if result.Status != "success" {
		return nil, fmt.Errorf("Prometheus query failed with status: %s", result.Status)
	}

	log.Printf("Retrieved %d results from Prometheus", len(result.Data.Result))
	return &result, nil
}

// convertRangeToInstantResult converts a range query result to instant query format
// by extracting unique source-destination pairs from all time series values
func (ic *IstioConnector) convertRangeToInstantResult(rangeResult *PrometheusQueryRangeResult) *PrometheusQueryResult {
	instantResult := &PrometheusQueryResult{
		Status: rangeResult.Status,
	}

	// Use a map to track unique metric combinations
	uniqueMetrics := make(map[string]struct {
		Metric map[string]string
		Seen   bool
	})

	for _, r := range rangeResult.Data.Result {
		// Create a key from the metric labels (excluding timestamp values)
		metricKey := fmt.Sprintf("%v", r.Metric)
		if _, exists := uniqueMetrics[metricKey]; !exists {
			uniqueMetrics[metricKey] = struct {
				Metric map[string]string
				Seen   bool
			}{
				Metric: r.Metric,
				Seen:   true,
			}
		}
	}

	// Convert to result format
	for _, v := range uniqueMetrics {
		instantResult.Data.Result = append(instantResult.Data.Result, struct {
			Metric map[string]string `json:"metric"`
			Value  []interface{}      `json:"value"`
		}{
			Metric: v.Metric,
			Value:  []interface{}{time.Now().Unix(), "1"}, // Dummy value for compatibility
		})
	}

	log.Printf("Retrieved %d unique metrics from Prometheus range query", len(instantResult.Data.Result))
	return instantResult
}

// ExtractAdjacencyList extracts source and destination workloads from Prometheus results
func ExtractAdjacencyList(result *PrometheusQueryResult) map[string][]string {
	adjacencyList := make(map[string][]string)

	for _, r := range result.Data.Result {
		source := r.Metric["source_workload"]
		destination := r.Metric["destination_workload"]

		if source != "" && destination != "" {
			if adjacencyList[source] == nil {
				adjacencyList[source] = make([]string, 0)
			}

			// Check if destination already exists
			exists := false
			for _, dest := range adjacencyList[source] {
				if dest == destination {
					exists = true
					break
				}
			}

			if !exists {
				adjacencyList[source] = append(adjacencyList[source], destination)
			}
		}
	}

	log.Printf("Extracted adjacency list with %d sources", len(adjacencyList))
	return adjacencyList
}

