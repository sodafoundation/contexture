package main

import (
	"log"
	"os"
	"strings"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/internal/server"
	"github.com/contexture/ocs/pkg/ocs/topology"
	chconnector "github.com/contexture/ocs/pkg/ocs/topology/clickhouse"
	"github.com/contexture/ocs/pkg/ocs/topology/mesh/istio"
	"github.com/gin-gonic/gin"
)

func main() {
	connectorType := strings.ToLower(os.Getenv("CONNECTOR"))
	if connectorType == "" {
		connectorType = "istio"
	}

	var conn topology.Connector
	var closable interface{ Close() error }

	switch connectorType {
	case "clickhouse":
		chConfig, err := config.LoadClickHouse()
		if err != nil {
			log.Fatalf("Load ClickHouse config: %v", err)
		}
		chConn, err := chconnector.Create(chConfig)
		if err != nil {
			log.Fatalf("Init ClickHouse connector: %v", err)
		}
		conn = chConn
		closable = chConn
		log.Printf("Using ClickHouse connector (%s:%d)", chConfig.Instances[0].Host, chConfig.Instances[0].Port)
	default:
		promConfig, err := config.LoadPrometheus()
		if err != nil {
			log.Fatalf("Load Prometheus config: %v", err)
		}
		log.Printf("Loaded Prometheus config, using URL: %s", promConfig.PrometheusInstances[0].BaseURL)
		conn = istio.Create(promConfig.PrometheusInstances[0].BaseURL)
		log.Printf("Using Istio/Prometheus connector")
	}

	srv := server.MustNewServer(conn)
	defer srv.Close()
	if closable != nil {
		defer func() {
			if err := closable.Close(); err != nil {
				log.Printf("Close connector: %v", err)
			}
		}()
	}

	router := gin.Default()
	router.GET("/", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"service":   "SODA Contexture OCS",
			"connector": connectorType,
			"endpoints": gin.H{
				"GET /health":              "Health check",
				"GET /get_ocs_prompt":      "OCS context for AI agents",
				"POST /collect_topology":   "Collect topology from data source",
				"POST /collect_istio_metrics": "Same as collect_topology (legacy)",
			},
		})
	})
	router.GET("/get_ocs_prompt", srv.GetOCSPromptHandler)
	router.POST("/collect_istio_metrics", srv.CollectTopologyHandler)
	router.POST("/collect_topology", srv.CollectTopologyHandler)
	router.GET("/health", srv.HealthCheckHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	log.Printf("Starting OCS server on port %s (connector=%s)", port, connectorType)
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("Run server: %v", err)
	}
}
