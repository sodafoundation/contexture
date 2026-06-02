package server

import (
	"log"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/internal/store"
	connectors "github.com/contexture/ocs/pkg/ocs/topology"
)

// Server holds HTTP server state and dependencies
type Server struct {
	ocsConfig *config.OCSConfig
	connector connectors.Connector
	store     store.TopologyStore
}

// New creates a new server with the given connector and store
func New(ocsConfig *config.OCSConfig, connector connectors.Connector, repo store.TopologyStore) *Server {
	return &Server{
		ocsConfig: ocsConfig,
		connector: connector,
		store:     repo,
	}
}

// Close closes all connections
func (s *Server) Close() error {
	return s.store.Close()
}

// OCSConfig returns the OCS configuration (for handlers)
func (s *Server) OCSConfig() *config.OCSConfig { return s.ocsConfig }

// Connector returns the topology connector
func (s *Server) Connector() connectors.Connector { return s.connector }

// Store returns the topology store
func (s *Server) Store() store.TopologyStore { return s.store }

// MustNewServer creates a new server by loading config and initializing connector and store.
// It is intended for use from main. For tests, use New with injected dependencies.
func MustNewServer(connector connectors.Connector) *Server {
	ocsConfig, err := config.LoadOCS()
	if err != nil {
		log.Fatalf("load OCS config: %v", err)
	}
	log.Printf("Loaded OCS config")

	repo, err := store.NewTopologyStore()
	if err != nil {
		log.Fatalf("init store: %v", err)
	}

	return New(ocsConfig, connector, repo)
}
