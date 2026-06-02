package server

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/internal/prompt"
	connectors "github.com/contexture/ocs/pkg/ocs/topology"
	"github.com/gin-gonic/gin"
)

// connectorPinger is implemented by connectors that support a live health ping.
type connectorPinger interface {
	Ping(ctx context.Context) error
}

// GetOCSPromptHandler handles GET /get_ocs_prompt
func (s *Server) GetOCSPromptHandler(c *gin.Context) {
	adjacencyList, err := s.store.GetLatestAdjacencyList()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  "error",
			"message": fmt.Sprintf("Failed to retrieve topology from MongoDB: %v", err),
		})
		return
	}

	if adjacencyList == nil {
		adjacencyList = make(connectors.AdjacencyList)
	}

	contextDefinitions := prompt.BuildContextDefinitions(adjacencyList, s.ocsConfig)
	response := config.OCSPromptResponse{
		SpecVersion:        "0.1",
		ContextDefinitions: contextDefinitions,
	}
	c.JSON(http.StatusOK, response)
}

// CollectTopologyHandler handles POST /collect_istio_metrics (or generic collect topology)
func (s *Server) CollectTopologyHandler(c *gin.Context) {
	if len(s.ocsConfig.Workload) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"status":  "error",
			"message": "No source workloads configured in ocs_config.yaml",
		})
		return
	}

	from, to, err := parseTimestampParams(c, s.ocsConfig)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"status":  "error",
			"message": err.Error(),
		})
		return
	}

	adjacencyList, err := s.connector.FetchTopology(s.ocsConfig.Workload, from, to)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"status":  "error",
			"message": fmt.Sprintf("Failed to fetch topology: %v", err),
		})
		return
	}

	docID, err := s.store.SaveAdjacencyList(adjacencyList)
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
		"connector":      s.connector.Name(),
	}

	if from != nil && to != nil {
		response["from_timestamp"] = from.Format(time.RFC3339)
		response["to_timestamp"] = to.Format(time.RFC3339)
		fromStr := c.Query("from_timestamp")
		toStr := c.Query("to_timestamp")
		if s.ocsConfig.TimeWindowMinutes != nil && fromStr == "" && toStr == "" {
			response["time_window_minutes"] = *s.ocsConfig.TimeWindowMinutes
		}
	}

	c.JSON(http.StatusOK, response)
}

// HealthCheckHandler handles GET /health
func (s *Server) HealthCheckHandler(c *gin.Context) {
	status := "healthy"
	connectorOK := s.connector != nil
	dataSourceOK := true

	if p, ok := s.connector.(connectorPinger); ok {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
		defer cancel()
		if err := p.Ping(ctx); err != nil {
			status = "degraded"
			dataSourceOK = false
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"status":            status,
		"connector":         s.connector.Name(),
		"connector_active":  connectorOK,
		"datasource_healthy": dataSourceOK,
		"mongodb":           s.store != nil,
		"timestamp":         time.Now().Format(time.RFC3339),
	})
}

func parseTimestampParams(c *gin.Context, cfg *config.OCSConfig) (*time.Time, *time.Time, error) {
	var from, to *time.Time
	fromStr := c.Query("from_timestamp")
	toStr := c.Query("to_timestamp")

	if fromStr != "" || toStr != "" {
		if fromStr != "" {
			t, err := parseTimestamp(fromStr)
			if err != nil {
				return nil, nil, fmt.Errorf("invalid from_timestamp format. Use RFC3339 or Unix timestamp: %v", err)
			}
			from = t
		}
		if toStr != "" {
			t, err := parseTimestamp(toStr)
			if err != nil {
				return nil, nil, fmt.Errorf("invalid to_timestamp format. Use RFC3339 or Unix timestamp: %v", err)
			}
			to = t
		}
		if from != nil && to != nil && from.After(*to) {
			return nil, nil, fmt.Errorf("from_timestamp must be before to_timestamp")
		}
		if (from != nil && to == nil) || (from == nil && to != nil) {
			return nil, nil, fmt.Errorf("both from_timestamp and to_timestamp must be provided together, or neither")
		}
	} else if cfg.TimeWindowMinutes != nil {
		now := time.Now()
		fromTime := now.Add(-time.Duration(*cfg.TimeWindowMinutes) * time.Minute)
		from = &fromTime
		to = &now
	}

	return from, to, nil
}

func parseTimestamp(s string) (*time.Time, error) {
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return &t, nil
	}
	if unixSec, err := strconv.ParseInt(s, 10, 64); err == nil {
		t := time.Unix(unixSec, 0)
		return &t, nil
	}
	return nil, fmt.Errorf("unable to parse timestamp")
}
