package store

import (
	"log"
	"os"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// TopologyStore saves workload adjacency for OCS prompts.
type TopologyStore interface {
	GetLatestAdjacencyList() (map[string][]string, error)
	SaveAdjacencyList(adjacencyList map[string][]string) (primitive.ObjectID, error)
	Close() error
}

// NewTopologyStore opens MongoDB unless MONGODB_URI=memory (in-process dev store).
func NewTopologyStore() (TopologyStore, error) {
	if os.Getenv("MONGODB_URI") == "memory" {
		log.Printf("Using in-memory topology store (MONGODB_URI=memory)")
		return newMemoryStore(), nil
	}
	return NewMongoRepository()
}
