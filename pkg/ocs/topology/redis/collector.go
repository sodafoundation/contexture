package redis

import (
	"context"
	"fmt"
	"log"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	rediscontext "github.com/contexture/ocs/pkg/ocs/context/redis"
	redislib "github.com/redis/go-redis/v9"
)

const (
	defaultScanCount      int64 = 200
	defaultSampleLimit          = 500
	defaultKeyspaceSampleLimit  = 5
)

// Inspector captures the Redis operations needed by the collector.
// This keeps the collection flow modular so a future MCP-backed inspector
// can implement SCAN/TYPE/HKEYS/TTL without changing the collector logic.
type Inspector interface {
	Scan(ctx context.Context, cursor uint64, match string, count int64) ([]string, uint64, error)
	Type(ctx context.Context, key string) (string, error)
	HKeys(ctx context.Context, key string) ([]string, error)
	TTL(ctx context.Context, key string) (time.Duration, error)
	Close() error
}

// Collector inspects Redis and builds metadata-only context.
type Collector struct {
	inspector           Inspector
	sampleLimit         int
	keyspaceSampleLimit int
}

// Create builds a collector using environment-driven Redis configuration.
func Create() (*Collector, error) {
	inspector, err := NewDirectInspectorFromEnv()
	if err != nil {
		return nil, err
	}
	return NewCollector(inspector), nil
}

// NewCollector builds a collector with the provided inspector.
func NewCollector(inspector Inspector) *Collector {
	return &Collector{
		inspector:           inspector,
		sampleLimit:         readIntEnv("REDIS_CONTEXT_SAMPLE_LIMIT", defaultSampleLimit),
		keyspaceSampleLimit: readIntEnv("REDIS_CONTEXT_KEYS_PER_PATTERN", defaultKeyspaceSampleLimit),
	}
}

// Close closes the underlying inspector connections if any.
func (c *Collector) Close() error {
	if c.inspector != nil {
		return c.inspector.Close()
	}
	return nil
}

// Collect scans Redis and generates a metadata-only description of keyspaces.
func (c *Collector) Collect(ctx context.Context) (*rediscontext.Context, error) {
	if c.inspector == nil {
		return nil, fmt.Errorf("redis inspector is not configured")
	}

	log.Printf("\n--- [DEBUG] Redis Context Collection Starting ---")

	type aggregate struct {
		pattern  string
		typeName string
		fields   map[string]struct{}
		hasTTL   bool
		samples  int
	}

	aggregates := make(map[string]*aggregate)
	processed := 0
	var cursor uint64

	for {
		log.Printf("    Scanning keys matching '*' from cursor: %d", cursor)
		keys, next, err := c.inspector.Scan(ctx, cursor, "*", defaultScanCount)
		if err != nil {
			log.Printf("    [ERROR] Scan keys failed: %v", err)
			return nil, fmt.Errorf("scan redis keys: %w", err)
		}

		log.Printf("    Scan returned %d keys to inspect", len(keys))
		for _, key := range keys {
			if processed >= c.sampleLimit {
				log.Printf("    [DEBUG] Reached keyspace sample limit of %d", c.sampleLimit)
				break
			}

			typeName, err := c.inspector.Type(ctx, key)
			if err != nil {
				log.Printf("    [WARN] Skip key %q, type error: %v", key, err)
				continue
			}

			pattern := inferPattern(key)
			log.Printf("    Key: %-30s | Type: %-8s | Pattern: %s", key, typeName, pattern)
			
			aggKey := pattern + "|" + typeName
			agg, exists := aggregates[aggKey]
			if !exists {
				agg = &aggregate{
					pattern:  pattern,
					typeName: typeName,
					fields:   make(map[string]struct{}),
				}
				aggregates[aggKey] = agg
			}

			ttl, err := c.inspector.TTL(ctx, key)
			if err == nil && ttl > 0 {
				agg.hasTTL = true
			}

			if typeName == "hash" && agg.samples < c.keyspaceSampleLimit {
				fields, err := c.inspector.HKeys(ctx, key)
				if err == nil {
					for _, field := range fields {
						agg.fields[field] = struct{}{}
					}
				} else {
					log.Printf("    [WARN] Failed to fetch hash fields for %q: %v", key, err)
				}
			}

			agg.samples++
			processed++
		}

		if processed >= c.sampleLimit || next == 0 {
			break
		}
		cursor = next
	}

	keyspaces := make([]rediscontext.KeyspaceMetadata, 0, len(aggregates))
	for _, agg := range aggregates {
		fields := setToSortedSlice(agg.fields)
		keyspaces = append(keyspaces, rediscontext.KeyspaceMetadata{
			Pattern:     agg.pattern,
			Type:        agg.typeName,
			Fields:      fields,
			TTL:         agg.hasTTL,
			Description: inferDescription(agg.pattern, agg.typeName, fields, agg.hasTTL),
		})
	}

	sort.Slice(keyspaces, func(i, j int) bool {
		if keyspaces[i].Pattern == keyspaces[j].Pattern {
			return keyspaces[i].Type < keyspaces[j].Type
		}
		return keyspaces[i].Pattern < keyspaces[j].Pattern
	})

	relationships := inferRelationships(keyspaces)
	log.Printf("\n--- [DEBUG] Inferred Redis Namespace Relationships ---")
	for _, rel := range relationships {
		log.Printf("    %s  -->  %s (%s)", rel.From, rel.To, rel.Reason)
	}
	log.Printf("------------------------------------------------------")

	result := &rediscontext.Context{
		Database:      "redis",
		Keyspaces:     keyspaces,
		Relationships: relationships,
		CollectedAt:   time.Now().UTC(),
	}

	log.Printf("redis collector: collected %d keyspace patterns from %d sampled keys", len(keyspaces), processed)
	return result, nil
}

// DirectInspector is a go-redis backed inspector used when no MCP transport is available.
// It mirrors the SCAN/TYPE/HKEYS/TTL operations required by the collector.
type DirectInspector struct {
	client *redislib.Client
}

// NewDirectInspectorFromEnv creates a direct inspector from environment configuration.
func NewDirectInspectorFromEnv() (*DirectInspector, error) {
	addr := os.Getenv("REDIS_ADDR")
	if addr == "" {
		addr = "localhost:6379"
	}

	db := readIntEnv("REDIS_DB", 0)
	client := redislib.NewClient(&redislib.Options{
		Addr:     addr,
		Password: os.Getenv("REDIS_PASSWORD"),
		DB:       db,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("connect to redis %s: %w", addr, err)
	}

	return &DirectInspector{client: client}, nil
}

func (d *DirectInspector) Scan(ctx context.Context, cursor uint64, match string, count int64) ([]string, uint64, error) {
	return d.client.Scan(ctx, cursor, match, count).Result()
}

func (d *DirectInspector) Type(ctx context.Context, key string) (string, error) {
	return d.client.Type(ctx, key).Result()
}

func (d *DirectInspector) HKeys(ctx context.Context, key string) ([]string, error) {
	return d.client.HKeys(ctx, key).Result()
}

func (d *DirectInspector) TTL(ctx context.Context, key string) (time.Duration, error) {
	return d.client.TTL(ctx, key).Result()
}

func (d *DirectInspector) Close() error {
	if d.client != nil {
		return d.client.Close()
	}
	return nil
}

func inferPattern(key string) string {
	parts := strings.Split(key, ":")
	if len(parts) == 1 {
		return key
	}

	for index := range parts {
		if looksDynamic(parts[index]) {
			parts[index] = "*"
		}
	}
	return strings.Join(parts, ":")
}

// uuidOrLongHexRe matches UUID-style identifiers and long hex blobs (8+ chars).
// Examples: "550e8400-e29b-41d4-a716-446655440000", "a3f2c1b0"
var uuidOrLongHexRe = regexp.MustCompile(`^[0-9a-fA-F-]{8,}$`)

// looksDynamic reports whether a colon-separated key segment looks like a
// dynamic runtime value (ID, counter, hash) rather than a stable namespace
// label. The heuristic is intentionally kept identical to the Python
// looks_dynamic_segment() function in app/mcp_server.py so that both the
// Go OCS collector and the Python MCP discover_schema tool produce the same
// pattern groupings for the same Redis keyspace.
//
// Rules (evaluated in order):
//  1. Empty segment  → stable (false)
//  2. Pure integer   → dynamic (e.g. "42", "1001")
//  3. UUID / long hex blob matching [0-9a-fA-F-]{8,} → dynamic
//  4. Mixed alphanumeric segment ≥ 8 chars that contains at least one digit
//     → dynamic (e.g. "prod001abc", "abc12345")
//  5. Otherwise      → stable (e.g. "user", "user-profile", "session_store")
func looksDynamic(part string) bool {
	if part == "" {
		return false
	}
	// Rule 2: pure integer
	allDigits := true
	for _, r := range part {
		if r < '0' || r > '9' {
			allDigits = false
			break
		}
	}
	if allDigits {
		return true
	}
	// Rule 3: UUID or long hex blob
	if uuidOrLongHexRe.MatchString(part) {
		return true
	}
	// Rule 4: mixed alphanumeric ID (≥ 8 chars, at least one digit)
	if len(part) >= 8 {
		hasDigit := false
		for _, r := range part {
			if r >= '0' && r <= '9' {
				hasDigit = true
				break
			}
		}
		if hasDigit {
			return true
		}
	}
	return false
}

func inferDescription(pattern, typeName string, fields []string, hasTTL bool) string {
	parts := []string{fmt.Sprintf("Redis %s keyspace", typeName)}
	if strings.Contains(pattern, "cache") || hasTTL {
		parts = append(parts, "likely cache-oriented")
	}
	if len(fields) > 0 {
		parts = append(parts, fmt.Sprintf("hash fields: %s", strings.Join(fields, ", ")))
	}
	return strings.Join(parts, "; ")
}

func inferRelationships(keyspaces []rediscontext.KeyspaceMetadata) []rediscontext.KeyspaceRelationship {
	relationships := make([]rediscontext.KeyspaceRelationship, 0)
	for _, source := range keyspaces {
		sourcePrefix := stablePrefix(source.Pattern)
		for _, target := range keyspaces {
			if source.Pattern == target.Pattern {
				continue
			}
			targetPrefix := stablePrefix(target.Pattern)
			if sourcePrefix == "" || targetPrefix == "" {
				continue
			}
			if strings.Contains(source.Pattern, targetPrefix) || strings.Contains(target.Pattern, sourcePrefix) {
				relationships = append(relationships, rediscontext.KeyspaceRelationship{
					From:   source.Pattern,
					To:     target.Pattern,
					Reason: "shared key namespace naming",
				})
			}
		}
	}
	return dedupeRelationships(relationships)
}

func stablePrefix(pattern string) string {
	parts := strings.Split(pattern, ":")
	stable := make([]string, 0, len(parts))
	for _, part := range parts {
		if part == "*" {
			break
		}
		stable = append(stable, part)
	}
	return strings.Join(stable, ":")
}

func dedupeRelationships(in []rediscontext.KeyspaceRelationship) []rediscontext.KeyspaceRelationship {
	seen := make(map[string]struct{}, len(in))
	out := make([]rediscontext.KeyspaceRelationship, 0, len(in))
	for _, rel := range in {
		key := rel.From + "|" + rel.To + "|" + rel.Reason
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, rel)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].From == out[j].From {
			return out[i].To < out[j].To
		}
		return out[i].From < out[j].From
	})
	return out
}

func setToSortedSlice(values map[string]struct{}) []string {
	if len(values) == 0 {
		return nil
	}
	out := make([]string, 0, len(values))
	for value := range values {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

func readIntEnv(key string, fallback int) int {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed <= 0 {
		return fallback
	}
	return parsed
}
