package redis

import "time"

// KeyspaceRelationship describes a possible relationship between two Redis keyspaces.
// The collector keeps this heuristic and metadata-only so no actual values are stored.
type KeyspaceRelationship struct {
	From   string `bson:"from" json:"from"`
	To     string `bson:"to" json:"to"`
	Reason string `bson:"reason,omitempty" json:"reason,omitempty"`
}

// KeyspaceMetadata describes the inferred structure of a Redis keyspace pattern.
type KeyspaceMetadata struct {
	Pattern     string   `bson:"pattern" json:"pattern"`
	Type        string   `bson:"type" json:"type"`
	Fields      []string `bson:"fields,omitempty" json:"fields,omitempty"`
	TTL         bool     `bson:"ttl" json:"ttl"`
	Description string   `bson:"description,omitempty" json:"description,omitempty"`
}

// Context is the MongoDB/API representation of collected Redis metadata.
type Context struct {
	Database      string                 `bson:"database" json:"database"`
	Keyspaces     []KeyspaceMetadata     `bson:"keyspaces" json:"keyspaces"`
	Relationships []KeyspaceRelationship `bson:"relationships,omitempty" json:"relationships,omitempty"`
	CollectedAt   time.Time              `bson:"collected_at,omitempty" json:"collected_at,omitempty"`
}
