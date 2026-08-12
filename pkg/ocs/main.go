package main

import (
	"log"
	"os"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/internal/server"
	"github.com/contexture/ocs/pkg/ocs/topology"
	"github.com/contexture/ocs/pkg/ocs/topology/mesh/istio"
	"github.com/gin-gonic/gin"
)

func main() {
	promConfig, err := config.LoadPrometheus()
	if err != nil {
		log.Fatalf("Load Prometheus config: %v", err)
	}
	log.Printf("Loaded Prometheus config, using URL: %s", promConfig.PrometheusInstances[0].BaseURL)

	var conn topology.Connector
	conn = istio.Create(promConfig.PrometheusInstances[0].BaseURL)

	srv := server.MustNewServer(conn)
	defer srv.Close()

	router := gin.Default()
	router.GET("/get_ocs_prompt", srv.GetOCSPromptHandler)
	router.GET("/get_redis_context", srv.GetRedisContextHandler)
	router.POST("/collect_istio_metrics", srv.CollectTopologyHandler)
	router.POST("/collect_redis_context", srv.CollectRedisContextHandler)
	router.GET("/health", srv.HealthCheckHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	log.Printf("Starting OCS server on port %s", port)
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("Run server: %v", err)
	}
}
