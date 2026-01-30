package main

import (
	"log"
	"os"

	"github.com/gin-gonic/gin"
)

func main() {
	// Initialize server
	server, err := NewServer()
	if err != nil {
		log.Fatalf("Failed to initialize server: %v", err)
	}
	defer server.Close()

	// Setup Gin router
	router := gin.Default()

	// Register routes
	router.GET("/get_ocs_prompt", server.getOCSPromptHandler)
	router.POST("/collect_istio_metrics", server.collectIstioMetricsHandler)
	router.GET("/health", server.healthCheckHandler)

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	log.Printf("Starting OCS server on port %s", port)
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
