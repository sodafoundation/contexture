package main

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// MetricConfig represents a metric configuration
type MetricConfig struct {
	Name             string                 `yaml:"name"`
	Type             string                 `yaml:"type"`
	Unit             string                 `yaml:"unit"`
	Description      string                 `yaml:"description"`
	AggregationLogic string                 `yaml:"aggregation_logic,omitempty"`
	HealthConfig     map[string]interface{} `yaml:"health_config,omitempty"`
}

// OCSConfig represents the OCS configuration structure
type OCSConfig struct {
	Policy            []string       `yaml:"policy"`
	Metrics           []MetricConfig `yaml:"metrics"`
	Workload          []string       `yaml:"workload"`
	TimeWindowMinutes *int           `yaml:"time_window_minutes"` // Optional: if set, use time window for queries
}

// PrometheusConfig represents Prometheus configuration
type PrometheusConfig struct {
	PrometheusInstances []struct {
		Name       string            `yaml:"name"`
		BaseURL    string            `yaml:"base_url"`
		Headers    map[string]string `yaml:"headers"`
		DisableSSL bool              `yaml:"disable_ssl"`
	} `yaml:"prometheus_instances"`
}

// PrometheusQueryResult represents a Prometheus instant query result
type PrometheusQueryResult struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Metric map[string]string `json:"metric"`
			Value  []interface{}     `json:"value"`
		} `json:"result"`
	} `json:"data"`
}

// PrometheusQueryRangeResult represents a Prometheus range query result
type PrometheusQueryRangeResult struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Metric map[string]string `json:"metric"`
			Values [][]interface{}   `json:"values"`
		} `json:"result"`
	} `json:"data"`
}

// AdjacencyListDocument represents the MongoDB document structure
type AdjacencyListDocument struct {
	ID               primitive.ObjectID  `bson:"_id,omitempty"`
	AdjacencyList    map[string][]string `bson:"adjacency_list"`
	Timestamp        time.Time           `bson:"timestamp"`
	SourceCount      int                 `bson:"source_count"`
	TotalConnections int                 `bson:"total_connections"`
}

// OCSContextDefinition represents a context definition in the OCS prompt response
type OCSContextDefinition struct {
	ResourceID string                 `json:"resource_id,omitempty"`
	Domain     string                 `json:"domain,omitempty"`
	Identity   map[string]interface{} `json:"identity,omitempty"`
	Metrics    []MetricConfig         `json:"metrics,omitempty"`
	Topology   map[string]interface{} `json:"topology,omitempty"`
	Policy     []string               `json:"policy,omitempty"`
}

// OCSPromptResponse represents the OCS prompt response structure
type OCSPromptResponse struct {
	SpecVersion        string                 `json:"spec_version"`
	ContextDefinitions []OCSContextDefinition `json:"context_definitions"`
}
