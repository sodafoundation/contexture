package clickhouse

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/contexture/ocs/pkg/ocs/internal/config"
	"github.com/contexture/ocs/pkg/ocs/topology"
)

// Connector loads workload topology from a ClickHouse table.
type Connector struct {
	cfg    *config.ClickHouseConfig
	conn   clickhouse.Conn
}

// Create opens a ClickHouse connection and returns a topology connector.
func Create(cfg *config.ClickHouseConfig) (*Connector, error) {
	conn, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{fmt.Sprintf("%s:%d", cfg.Instances[0].Host, nonZeroPort(cfg.Instances[0].Port))},
		Auth: clickhouse.Auth{
			Database: defaultDB(cfg.Instances[0].Database),
			Username: defaultUser(cfg.Instances[0].Username),
			Password: cfg.Instances[0].Password,
		},
		TLS: nil,
	})
	if err != nil {
		return nil, fmt.Errorf("open ClickHouse: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := conn.Ping(ctx); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("ping ClickHouse: %w", err)
	}

	log.Printf("Connected to ClickHouse at %s", cfg.Instances[0].Host)
	return &Connector{cfg: cfg, conn: conn}, nil
}

func nonZeroPort(p int) int {
	if p == 0 {
		return 9000
	}
	return p
}

func defaultDB(db string) string {
	if db == "" {
		return "default"
	}
	return db
}

func defaultUser(user string) string {
	if user == "" {
		return "default"
	}
	return user
}

// Name implements topology.Connector.
func (c *Connector) Name() string {
	return "clickhouse"
}

// Ping checks ClickHouse connectivity.
func (c *Connector) Ping(ctx context.Context) error {
	return c.conn.Ping(ctx)
}

// Close closes the ClickHouse connection.
func (c *Connector) Close() error {
	if c.conn != nil {
		return c.conn.Close()
	}
	return nil
}

// FetchTopology implements topology.Connector.
func (c *Connector) FetchTopology(sourceWorkloads []string, from, to *time.Time) (topology.AdjacencyList, error) {
	if len(sourceWorkloads) == 0 {
		return nil, fmt.Errorf("no source workloads provided")
	}

	t := c.cfg.Topology
	placeholders := make([]string, len(sourceWorkloads))
	args := make([]interface{}, 0, len(sourceWorkloads)+2)
	for i, w := range sourceWorkloads {
		placeholders[i] = "?"
		args = append(args, w)
	}

	query := fmt.Sprintf(
		`SELECT DISTINCT %s, %s FROM %s WHERE %s IN (%s)`,
		quoteIdent(t.SourceColumn),
		quoteIdent(t.DestinationColumn),
		quoteIdent(t.Table),
		quoteIdent(t.SourceColumn),
		strings.Join(placeholders, ", "),
	)

	if from != nil && to != nil {
		query += fmt.Sprintf(" AND %s >= ? AND %s <= ?", quoteIdent(t.TimeColumn), quoteIdent(t.TimeColumn))
		args = append(args, *from, *to)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	rows, err := c.conn.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("ClickHouse query failed: %w", err)
	}
	defer rows.Close()

	adjacencyList := make(topology.AdjacencyList)
	for rows.Next() {
		var source, destination string
		if err := rows.Scan(&source, &destination); err != nil {
			return nil, fmt.Errorf("scan row: %w", err)
		}
		if source == "" || destination == "" {
			continue
		}
		if !contains(adjacencyList[source], destination) {
			adjacencyList[source] = append(adjacencyList[source], destination)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	log.Printf("ClickHouse: extracted adjacency list with %d sources", len(adjacencyList))
	return adjacencyList, nil
}

func quoteIdent(name string) string {
	return name
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}
