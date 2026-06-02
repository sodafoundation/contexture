package store

import (
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

type memoryEntry struct {
	id            primitive.ObjectID
	adjacencyList map[string][]string
	timestamp     time.Time
}

type memoryStore struct {
	mu       sync.RWMutex
	entries  []memoryEntry
}

func newMemoryStore() *memoryStore {
	return &memoryStore{}
}

func (m *memoryStore) GetLatestAdjacencyList() (map[string][]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if len(m.entries) == 0 {
		return nil, nil
	}
	latest := m.entries[len(m.entries)-1]
	out := make(map[string][]string, len(latest.adjacencyList))
	for k, v := range latest.adjacencyList {
		cp := make([]string, len(v))
		copy(cp, v)
		out[k] = cp
	}
	return out, nil
}

func (m *memoryStore) SaveAdjacencyList(adjacencyList map[string][]string) (primitive.ObjectID, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	copied := make(map[string][]string, len(adjacencyList))
	for k, v := range adjacencyList {
		cp := make([]string, len(v))
		copy(cp, v)
		copied[k] = cp
	}

	id := primitive.NewObjectID()
	m.entries = append(m.entries, memoryEntry{
		id:            id,
		adjacencyList: copied,
		timestamp:     time.Now(),
	})
	return id, nil
}

func (m *memoryStore) Close() error {
	return nil
}

var _ TopologyStore = (*MongoRepository)(nil)
var _ TopologyStore = (*memoryStore)(nil)
