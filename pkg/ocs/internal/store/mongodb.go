package store

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	rediscontext "github.com/contexture/ocs/pkg/ocs/context/redis"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// AdjacencyListDocument is the MongoDB document for workload adjacency
type AdjacencyListDocument struct {
	ID               primitive.ObjectID  `bson:"_id,omitempty"`
	AdjacencyList    map[string][]string `bson:"adjacency_list"`
	Timestamp        time.Time           `bson:"timestamp"`
	SourceCount      int                 `bson:"source_count"`
	TotalConnections int                 `bson:"total_connections"`
}

// Repository handles MongoDB operations for topology and context storage
type Repository struct {
	client              *mongo.Client
	adjacencyCollection *mongo.Collection
	redisCollection     *mongo.Collection
	isOffline           bool
}

// NewRepository creates a new MongoDB repository
func NewRepository() (*Repository, error) {
	mongoURI := os.Getenv("MONGODB_URI")
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017/"
	}

	dbName := os.Getenv("MONGODB_DB_NAME")
	if dbName == "" {
		dbName = "ocs"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Printf("Warning: failed to connect to MongoDB: %v. Running in offline store mode.", err)
		return &Repository{isOffline: true}, nil
	}

	if err := client.Ping(ctx, nil); err != nil {
		log.Printf("Warning: failed to ping MongoDB: %v. Running in offline store mode.", err)
		return &Repository{isOffline: true}, nil
	}

	database := client.Database(dbName)
	log.Printf("Connected to MongoDB: %s, database: %s", mongoURI, dbName)

	redisCollection := database.Collection("redis_context")

	// Configurable retention
	retentionStr := os.Getenv("REDIS_CONTEXT_RETENTION")
	if retentionStr == "" {
		retentionStr = "24h" // Default to 24 hours
	}
	retention, err := time.ParseDuration(retentionStr)
	if err != nil {
		log.Printf("Invalid REDIS_CONTEXT_RETENTION %q, defaulting to 24h: %v", retentionStr, err)
		retention = 24 * time.Hour
	}

	// Ensure TTL index
	if retention > 0 {
		indexModel := mongo.IndexModel{
			Keys:    bson.D{{Key: "collected_at", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(int32(retention.Seconds())),
		}
		if _, err := redisCollection.Indexes().CreateOne(ctx, indexModel); err != nil {
			log.Printf("Failed to create TTL index on redis_context (it may already exist with a different TTL): %v", err)
		}
	}

	return &Repository{
		client:              client,
		adjacencyCollection: database.Collection("workload_adjacency"),
		redisCollection:     redisCollection,
		isOffline:           false,
	}, nil
}

// Close closes the MongoDB connection
func (r *Repository) Close() error {
	if r.isOffline {
		return nil
	}
	if r.client != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return r.client.Disconnect(ctx)
	}
	return nil
}

// GetLatestAdjacencyList returns the most recent adjacency list
func (r *Repository) GetLatestAdjacencyList() (map[string][]string, error) {
	if r.isOffline {
		return make(map[string][]string), nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var doc AdjacencyListDocument
	opts := options.FindOne().SetSort(bson.D{{Key: "timestamp", Value: -1}})
	err := r.adjacencyCollection.FindOne(ctx, bson.D{}, opts).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to query MongoDB: %w", err)
	}

	return doc.AdjacencyList, nil
}

// SaveAdjacencyList persists an adjacency list and returns its document ID
func (r *Repository) SaveAdjacencyList(adjacencyList map[string][]string) (primitive.ObjectID, error) {
	if r.isOffline {
		return primitive.NewObjectID(), nil
	}
	totalConnections := 0
	for _, dests := range adjacencyList {
		totalConnections += len(dests)
	}

	doc := AdjacencyListDocument{
		ID:               primitive.NewObjectID(),
		AdjacencyList:    adjacencyList,
		Timestamp:        time.Now(),
		SourceCount:      len(adjacencyList),
		TotalConnections: totalConnections,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if docBytes, err := json.MarshalIndent(doc, "", "  "); err == nil {
		log.Printf("\n--- [DEBUG] Saving Document to MongoDB ---\n%s\n-----------------------------------------", string(docBytes))
	}

	result, err := r.adjacencyCollection.InsertOne(ctx, doc)
	if err != nil {
		return primitive.NilObjectID, fmt.Errorf("failed to insert document: %w", err)
	}

	log.Printf("Saved adjacency list to MongoDB with ID: %s", result.InsertedID)
	return result.InsertedID.(primitive.ObjectID), nil
}

// GetLatestRedisContext returns the most recent Redis context document.
func (r *Repository) GetLatestRedisContext() (*rediscontext.Context, error) {
	if r.isOffline {
		return nil, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var doc rediscontext.Context
	opts := options.FindOne().SetSort(bson.D{{Key: "collected_at", Value: -1}, {Key: "timestamp", Value: -1}})
	err := r.redisCollection.FindOne(ctx, bson.D{}, opts).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to query Redis context from MongoDB: %w", err)
	}

	return &doc, nil
}

// SaveRedisContext persists a Redis metadata snapshot and returns its document ID.
func (r *Repository) SaveRedisContext(redisCtx *rediscontext.Context) (primitive.ObjectID, error) {
	if r.isOffline {
		return primitive.NewObjectID(), nil
	}
	if redisCtx == nil {
		return primitive.NilObjectID, fmt.Errorf("redis context is nil")
	}
	if redisCtx.CollectedAt.IsZero() {
		redisCtx.CollectedAt = time.Now().UTC()
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if docBytes, err := json.MarshalIndent(redisCtx, "", "  "); err == nil {
		log.Printf("\n--- [DEBUG] Saving Redis Context to MongoDB ---\n%s\n-----------------------------------------------", string(docBytes))
	}

	result, err := r.redisCollection.InsertOne(ctx, redisCtx)
	if err != nil {
		return primitive.NilObjectID, fmt.Errorf("failed to insert Redis context: %w", err)
	}

	objectID, ok := result.InsertedID.(primitive.ObjectID)
	if !ok {
		return primitive.NilObjectID, fmt.Errorf("unexpected Redis context inserted ID type %T", result.InsertedID)
	}
	log.Printf("Saved Redis context to MongoDB with ID: %s", objectID.Hex())
	return objectID, nil
}

// SaveOCSContext persists the fully built OCS context definitions to MongoDB.
func (r *Repository) SaveOCSContext(contextDefinitions interface{}) error {
	if r.isOffline {
		return nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	coll := r.client.Database("ocs").Collection("ocs_context_definitions")
	doc := bson.M{
		"context_definitions": contextDefinitions,
		"timestamp":           time.Now(),
	}

	_, err := coll.InsertOne(ctx, doc)
	if err != nil {
		return fmt.Errorf("failed to save OCS context definitions: %w", err)
	}
	log.Printf("Successfully saved OCS context definitions to MongoDB")
	return nil
}
