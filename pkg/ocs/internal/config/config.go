package config

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// LoadOCS loads the OCS configuration from YAML file
func LoadOCS() (*OCSConfig, error) {
	configPath := filepath.Join(filepath.Dir(os.Args[0]), "pkg/ocs/ocs_config_v2.yaml")
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		configPath = "pkg/ocs/ocs_config_v2.yaml"
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read OCS config: %w", err)
	}

	var cfg OCSConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse OCS config: %w", err)
	}

	return &cfg, nil
}

// LoadPrometheus loads Prometheus configuration
func LoadPrometheus() (*PrometheusConfig, error) {
	configPath := "config/prometheus_config.yaml"
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("prometheus config not found: %s", configPath)
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read Prometheus config: %w", err)
	}

	var cfg PrometheusConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("failed to parse Prometheus config: %w", err)
	}

	if len(cfg.PrometheusInstances) == 0 {
		return nil, fmt.Errorf("no Prometheus instances configured")
	}

	return &cfg, nil
}
