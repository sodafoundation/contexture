package main

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// loadOCSConfig loads the OCS configuration from YAML file
func loadOCSConfig() (*OCSConfig, error) {
	configPath := filepath.Join(filepath.Dir(os.Args[0]), "pkg/ocs/ocs_config.yaml")
	// Try relative path if absolute doesn't work
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		configPath = "pkg/ocs/ocs_config.yaml"
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read OCS config: %w", err)
	}

	var config OCSConfig
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse OCS config: %w", err)
	}

	return &config, nil
}

// loadPrometheusConfig loads Prometheus configuration
func loadPrometheusConfig() (*PrometheusConfig, error) {
	configPath := "config/prometheus_config.yaml"
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("prometheus config not found: %s", configPath)
	}

	data, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read Prometheus config: %w", err)
	}

	var config PrometheusConfig
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse Prometheus config: %w", err)
	}

	if len(config.PrometheusInstances) == 0 {
		return nil, fmt.Errorf("no Prometheus instances configured")
	}

	return &config, nil
}

