package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// ClickHouseInstance is one ClickHouse connection target.
type ClickHouseInstance struct {
	Name     string `yaml:"name"`
	Host     string `yaml:"host"`
	Port     int    `yaml:"port"`
	Database string `yaml:"database"`
	Username string `yaml:"username"`
	Password string `yaml:"password"`
	Secure   bool   `yaml:"secure"`
}

// ClickHouseTopologyMapping maps YAML fields to table columns for topology queries.
type ClickHouseTopologyMapping struct {
	Table              string `yaml:"table"`
	SourceColumn       string `yaml:"source_column"`
	DestinationColumn  string `yaml:"destination_column"`
	TimeColumn         string `yaml:"time_column"`
}

// ClickHouseConfig is the ClickHouse connector configuration.
type ClickHouseConfig struct {
	Instances []ClickHouseInstance      `yaml:"clickhouse_instances"`
	Topology  ClickHouseTopologyMapping `yaml:"topology"`
}

// LoadClickHouse loads ClickHouse configuration from config/clickhouse_config.yaml.
func LoadClickHouse() (*ClickHouseConfig, error) {
	configPath := os.Getenv("CLICKHOUSE_CONFIG_PATH")
	if configPath == "" {
		configPath = "config/clickhouse_config.yaml"
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read ClickHouse config: %w", err)
	}

	var cfg ClickHouseConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse ClickHouse config: %w", err)
	}

	if len(cfg.Instances) == 0 {
		return nil, fmt.Errorf("no ClickHouse instances configured")
	}

	if cfg.Topology.Table == "" {
		return nil, fmt.Errorf("topology.table is required in ClickHouse config")
	}
	if cfg.Topology.SourceColumn == "" || cfg.Topology.DestinationColumn == "" {
		return nil, fmt.Errorf("topology source/destination columns are required")
	}
	if cfg.Topology.TimeColumn == "" {
		cfg.Topology.TimeColumn = "event_time"
	}

	for _, name := range []string{cfg.Topology.Table, cfg.Topology.SourceColumn, cfg.Topology.DestinationColumn, cfg.Topology.TimeColumn} {
		if !isSQLIdent(name) {
			return nil, fmt.Errorf("invalid SQL identifier in ClickHouse config: %q", name)
		}
	}

	return &cfg, nil
}

func isSQLIdent(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_' {
			continue
		}
		return false
	}
	return true
}

// DSN returns a clickhouse-go connection string for the first configured instance.
func (c *ClickHouseConfig) DSN() string {
	inst := c.Instances[0]
	port := inst.Port
	if port == 0 {
		port = 9000
	}
	scheme := "clickhouse"
	if inst.Secure {
		scheme = "clickhouses"
	}
	user := inst.Username
	if user == "" {
		user = "default"
	}
	db := inst.Database
	if db == "" {
		db = "default"
	}
	return fmt.Sprintf("%s://%s:%s@%s:%d/%s", scheme, user, inst.Password, inst.Host, port, db)
}
