package server

import (
	"context"
	"log"
	"os"
	"time"

	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/internal/store"
	connectors "github.com/contexture/ocs/pkg/ocs/topology"
	rediscollector "github.com/contexture/ocs/pkg/ocs/topology/redis"
	rediscontext "github.com/contexture/ocs/pkg/ocs/context/redis"
	"go.mongodb.org/mongo-driver/bson/primitive"
)

// Store defines the interface for database operations
type Store interface {
	GetLatestAdjacencyList() (map[string][]string, error)
	SaveAdjacencyList(adjacencyList map[string][]string) (primitive.ObjectID, error)
	GetLatestRedisContext() (*rediscontext.Context, error)
	SaveRedisContext(redisCtx *rediscontext.Context) (primitive.ObjectID, error)
	SaveOCSContext(contextDefinitions interface{}) error
	Close() error
}

// Server holds HTTP server state and dependencies
type Server struct {
	ocsConfig      *config.OCSConfig
	connector      connectors.Connector
	redisCollector *rediscollector.Collector
	store          Store
	prometheusURL  string
	cancel         context.CancelFunc
}

// New creates a new server with the given connector and store
func New(ocsConfig *config.OCSConfig, connector connectors.Connector, redisCollector *rediscollector.Collector, repo Store, prometheusURL string) *Server {
	ctx, cancel := context.WithCancel(context.Background())
	s := &Server{
		ocsConfig:      ocsConfig,
		connector:      connector,
		redisCollector: redisCollector,
		store:          repo,
		prometheusURL:  prometheusURL,
		cancel:         cancel,
	}
	s.startBackgroundTasks(ctx)
	return s
}

func (s *Server) startBackgroundTasks(ctx context.Context) {
	if s.redisCollector == nil {
		return
	}
	intervalStr := os.Getenv("REDIS_CONTEXT_REFRESH_INTERVAL")
	if intervalStr == "" || intervalStr == "0" {
		return // disabled by default or explicitly disabled
	}
	interval, err := time.ParseDuration(intervalStr)
	if err != nil || interval <= 0 {
		log.Printf("Invalid REDIS_CONTEXT_REFRESH_INTERVAL %q: %v", intervalStr, err)
		return
	}

	log.Printf("Starting background Redis context refresh every %s", interval)
	go func() {
		ticker := time.NewTicker(interval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				log.Printf("Background refresh: collecting Redis context...")
				timeoutCtx, timeoutCancel := context.WithTimeout(ctx, 30*time.Second)
				redisCtx, err := s.redisCollector.Collect(timeoutCtx)
				timeoutCancel()
				if err != nil {
					log.Printf("Background refresh failed to collect: %v", err)
					continue
				}
				if _, err := s.store.SaveRedisContext(redisCtx); err != nil {
					log.Printf("Background refresh failed to save: %v", err)
				}
			}
		}
	}()
}

// Close closes all connections
func (s *Server) Close() error {
	if s.cancel != nil {
		s.cancel()
	}
	var lastErr error
	if s.redisCollector != nil {
		if err := s.redisCollector.Close(); err != nil {
			log.Printf("Failed to close redis collector: %v", err)
			lastErr = err
		}
	}
	if err := s.store.Close(); err != nil {
		log.Printf("Failed to close store: %v", err)
		lastErr = err
	}
	return lastErr
}

// OCSConfig returns the OCS configuration (for handlers)
func (s *Server) OCSConfig() *config.OCSConfig { return s.ocsConfig }

// Connector returns the topology connector
func (s *Server) Connector() connectors.Connector { return s.connector }

// RedisCollector returns the Redis context collector.
func (s *Server) RedisCollector() *rediscollector.Collector { return s.redisCollector }

// Store returns the repository
func (s *Server) Store() Store { return s.store }

// PrometheusURL returns the Prometheus base URL
func (s *Server) PrometheusURL() string { return s.prometheusURL }

// MustNewServer creates a new server by loading config and initializing connector and store.
// It is intended for use from main. For tests, use New with injected dependencies.
func MustNewServer(connector connectors.Connector) *Server {
	ocsConfig, err := config.LoadOCS()
	if err != nil {
		log.Fatalf("load OCS config: %v", err)
	}
	log.Printf("Loaded OCS config")

	promConfig, err := config.LoadPrometheus()
	var prometheusURL string
	if err != nil {
		log.Printf("Warning: load Prometheus config: %v. Running without live Prometheus metadata.", err)
	} else if len(promConfig.PrometheusInstances) > 0 {
		prometheusURL = promConfig.PrometheusInstances[0].BaseURL
	}

	repo, err := store.NewRepository()
	if err != nil {
		log.Fatalf("init store: %v", err)
	}

	redisCollector, err := rediscollector.Create()
	if err != nil {
		log.Printf("Redis collector not initialized: %v", err)
	}

	return New(ocsConfig, connector, redisCollector, repo, prometheusURL)
}
