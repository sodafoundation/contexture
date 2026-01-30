package main

import (
	"fmt"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

// Server holds the server state
type Server struct {
	ocsConfig      *OCSConfig
	istioConnector *IstioConnector
	mongoRepo      *MongoDBRepository
}

// NewServer creates a new server instance
func NewServer() (*Server, error) {
	// Load configurations
	ocsConfig, err := loadOCSConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load OCS config: %w", err)
	}
	log.Printf("Loaded OCS config")

	promConfig, err := loadPrometheusConfig()
	if err != nil {
		return nil, fmt.Errorf("failed to load Prometheus config: %w", err)
	}
	log.Printf("Loaded Prometheus config, using URL: %s", promConfig.PrometheusInstances[0].BaseURL)

	// Initialize Istio connector
	istioConnector := NewIstioConnector(promConfig.PrometheusInstances[0].BaseURL)

	// Initialize MongoDB repository
	mongoRepo, err := NewMongoDBRepository()
	if err != nil {
		return nil, fmt.Errorf("failed to initialize MongoDB: %w", err)
	}

	return &Server{
		ocsConfig:      ocsConfig,
		istioConnector: istioConnector,
		mongoRepo:      mongoRepo,
	}, nil
}

// Close closes all connections
func (s *Server) Close() error {
	return s.mongoRepo.Close()
}

// getOCSPromptHandler handles the get_ocs_prompt endpoint
func (s *Server) getOCSPromptHandler(c *gin.Context) {
	// Get latest topology from MongoDB
	adjacencyList, err := s.mongoRepo.GetLatestAdjacencyList()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  "error",
			"message": fmt.Sprintf("Failed to retrieve topology from MongoDB: %v", err),
		})
		return
	}

	// Initialize empty map if nil
	if adjacencyList == nil {
		adjacencyList = make(map[string][]string)
	}

	// Build context definitions
	contextDefinitions := buildContextDefinitions(adjacencyList, s.ocsConfig)

	// Build response
	response := OCSPromptResponse{
		SpecVersion:        "0.1",
		ContextDefinitions: contextDefinitions,
	}

	c.JSON(http.StatusOK, response)
}

// collectIstioMetricsHandler handles the collect_istio_metrics endpoint
func (s *Server) collectIstioMetricsHandler(c *gin.Context) {
	if len(s.ocsConfig.Workload) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"status":  "error",
			"message": "No source workloads configured in ocs_config.yaml",
		})
		return
	}

	// Parse and validate timestamps
	fromTimestamp, toTimestamp, err := parseTimestampParams(c, s.ocsConfig)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"status":  "error",
			"message": err.Error(),
		})
		return
	}

	// Query Prometheus via Istio connector
	result, err := s.istioConnector.QueryMetrics(s.ocsConfig.Workload, fromTimestamp, toTimestamp)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  "error",
			"message": fmt.Sprintf("Failed to query Prometheus: %v", err),
		})
		return
	}

	// Extract source and destination
	adjacencyList := ExtractAdjacencyList(result)

	// Save to MongoDB
	docID, err := s.mongoRepo.SaveAdjacencyList(adjacencyList)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  "error",
			"message": fmt.Sprintf("Failed to save to MongoDB: %v", err),
		})
		return
	}

	response := gin.H{
		"status":         "success",
		"message":        "Metrics collected and saved to MongoDB",
		"adjacency_list": adjacencyList,
		"document_id":    docID.Hex(),
		"timestamp":      time.Now().Format(time.RFC3339),
	}

	if fromTimestamp != nil && toTimestamp != nil {
		response["from_timestamp"] = fromTimestamp.Format(time.RFC3339)
		response["to_timestamp"] = toTimestamp.Format(time.RFC3339)

		// If time window was used from config, include that info
		fromStr := c.Query("from_timestamp")
		toStr := c.Query("to_timestamp")
		if s.ocsConfig.TimeWindowMinutes != nil && fromStr == "" && toStr == "" {
			response["time_window_minutes"] = *s.ocsConfig.TimeWindowMinutes
		}
	}

	c.JSON(http.StatusOK, response)
}

// healthCheckHandler handles health check endpoint
func (s *Server) healthCheckHandler(c *gin.Context) {
	response := gin.H{
		"status":     "healthy",
		"prometheus": s.istioConnector.prometheusURL != "",
		"mongodb":    s.mongoRepo != nil,
		"timestamp":  time.Now().Format(time.RFC3339),
	}
	c.JSON(http.StatusOK, response)
}

// parseTimestampParams parses and validates timestamp query parameters
func parseTimestampParams(c *gin.Context, config *OCSConfig) (*time.Time, *time.Time, error) {
	var fromTimestamp, toTimestamp *time.Time

	// Check if timestamps are provided in query parameters
	fromStr := c.Query("from_timestamp")
	toStr := c.Query("to_timestamp")

	if fromStr != "" || toStr != "" {
		// Parse provided timestamps
		if fromStr != "" {
			fromTime, err := parseTimestamp(fromStr)
			if err != nil {
				return nil, nil, fmt.Errorf("invalid from_timestamp format. Use RFC3339 (e.g., 2024-01-01T00:00:00Z) or Unix timestamp: %v", err)
			}
			fromTimestamp = fromTime
		}

		if toStr != "" {
			toTime, err := parseTimestamp(toStr)
			if err != nil {
				return nil, nil, fmt.Errorf("invalid to_timestamp format. Use RFC3339 (e.g., 2024-01-01T00:00:00Z) or Unix timestamp: %v", err)
			}
			toTimestamp = toTime
		}

		// Validate timestamp range
		if fromTimestamp != nil && toTimestamp != nil {
			if fromTimestamp.After(*toTimestamp) {
				return nil, nil, fmt.Errorf("from_timestamp must be before to_timestamp")
			}
		} else if (fromTimestamp != nil && toTimestamp == nil) || (fromTimestamp == nil && toTimestamp != nil) {
			return nil, nil, fmt.Errorf("both from_timestamp and to_timestamp must be provided together, or neither")
		}
	} else if config.TimeWindowMinutes != nil {
		// No timestamps provided, but time window is configured - use it
		now := time.Now()
		windowDuration := time.Duration(*config.TimeWindowMinutes) * time.Minute
		fromTime := now.Add(-windowDuration)
		fromTimestamp = &fromTime
		toTimestamp = &now
	}

	return fromTimestamp, toTimestamp, nil
}

// parseTimestamp parses a timestamp string in RFC3339 or Unix format
func parseTimestamp(timestampStr string) (*time.Time, error) {
	// Try RFC3339 first
	if t, err := time.Parse(time.RFC3339, timestampStr); err == nil {
		return &t, nil
	}

	// Try Unix timestamp
	if unixSec, err := strconv.ParseInt(timestampStr, 10, 64); err == nil {
		t := time.Unix(unixSec, 0)
		return &t, nil
	}

	return nil, fmt.Errorf("unable to parse timestamp")
}

// buildContextDefinitions builds context definitions from adjacency list and config
func buildContextDefinitions(adjacencyList map[string][]string, config *OCSConfig) []OCSContextDefinition {
	var contextDefinitions []OCSContextDefinition

	// Create a context definition for each workload
	workloadSet := make(map[string]bool)

	// Collect all workloads (sources and destinations)
	for source, destinations := range adjacencyList {
		workloadSet[source] = true
		for _, dest := range destinations {
			workloadSet[dest] = true
		}
	}

	// Also include workloads from config that might not be in topology yet
	for _, workload := range config.Workload {
		workloadSet[workload] = true
	}

	// Create context definition for each workload
	for workload := range workloadSet {
		contextDef := OCSContextDefinition{
			ResourceID: fmt.Sprintf("workload-%s", workload),
			Domain:     "compute.k8s",
			Identity: map[string]interface{}{
				"workload": workload,
			},
			Metrics: config.Metrics,
			Policy:  config.Policy,
		}

		// Build topology from adjacency list
		topology := buildTopology(adjacencyList, workload)
		if len(topology) > 0 {
			contextDef.Topology = topology
		}

		contextDefinitions = append(contextDefinitions, contextDef)
	}

	return contextDefinitions
}

// buildTopology builds topology information for a specific workload
func buildTopology(adjacencyList map[string][]string, workload string) map[string]interface{} {
	topology := make(map[string]interface{})

	// Add dependencies (destinations this workload connects to)
	if destinations, exists := adjacencyList[workload]; exists && len(destinations) > 0 {
		topology["dependencies"] = destinations
	}

	// Add reverse dependencies (workloads that connect to this one)
	var reverseDeps []string
	for source, destinations := range adjacencyList {
		for _, dest := range destinations {
			if dest == workload {
				reverseDeps = append(reverseDeps, source)
			}
		}
	}
	if len(reverseDeps) > 0 {
		topology["dependents"] = reverseDeps
	}

	return topology
}
