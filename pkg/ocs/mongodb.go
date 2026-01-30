package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// MongoDBRepository handles all MongoDB operations
type MongoDBRepository struct {
	client     *mongo.Client
	database   *mongo.Database
	collection *mongo.Collection
}

// NewMongoDBRepository creates a new MongoDB repository
func NewMongoDBRepository() (*MongoDBRepository, error) {
	mongoURI := os.Getenv("MONGODB_URI")
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017/"
	}

	dbName := os.Getenv("MONGODB_DB_NAME")
	if dbName == "" {
		dbName = "ocs"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		return nil, fmt.Errorf("failed to connect to MongoDB: %w", err)
	}

	// Test connection
	if err := client.Ping(ctx, nil); err != nil {
		return nil, fmt.Errorf("failed to ping MongoDB: %w", err)
	}

	database := client.Database(dbName)
	collection := database.Collection("workload_adjacency")

	log.Printf("Connected to MongoDB: %s, database: %s", mongoURI, dbName)

	return &MongoDBRepository{
		client:     client,
		database:   database,
		collection: collection,
	}, nil
}

// Close closes the MongoDB connection
func (r *MongoDBRepository) Close() error {
	if r.client != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return r.client.Disconnect(ctx)
	}
	return nil
}

// GetLatestAdjacencyList retrieves the most recent adjacency list from MongoDB
func (r *MongoDBRepository) GetLatestAdjacencyList() (map[string][]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Find the latest document sorted by timestamp
	var doc AdjacencyListDocument
	opts := options.FindOne().SetSort(bson.D{{Key: "timestamp", Value: -1}})
	err := r.collection.FindOne(ctx, bson.D{}, opts).Decode(&doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, nil // No documents found, return nil
		}
		return nil, fmt.Errorf("failed to query MongoDB: %w", err)
	}

	return doc.AdjacencyList, nil
}

// SaveAdjacencyList saves the adjacency list to MongoDB
func (r *MongoDBRepository) SaveAdjacencyList(adjacencyList map[string][]string) (primitive.ObjectID, error) {
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

	result, err := r.collection.InsertOne(ctx, doc)
	if err != nil {
		return primitive.NilObjectID, fmt.Errorf("failed to insert document: %w", err)
	}

	log.Printf("Saved adjacency list to MongoDB with ID: %s", result.InsertedID)
	return result.InsertedID.(primitive.ObjectID), nil
}

