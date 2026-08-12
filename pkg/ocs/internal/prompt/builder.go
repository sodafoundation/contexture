package prompt

import (
	"context"
	"fmt"
	"strconv"
	"strings"


	"github.com/contexture/ocs/pkg/ocs/internal/config"
	connectors "github.com/contexture/ocs/pkg/ocs/topology"
)

// BuildContextDefinitions builds OCS context definitions from adjacency list, config, and live Prometheus discovery
func BuildContextDefinitions(ctx context.Context, adjacencyList connectors.AdjacencyList, cfg *config.OCSConfig, discoverer *PrometheusDiscoverer) []config.OCSContextDefinition {
	if adjacencyList == nil {
		adjacencyList = make(connectors.AdjacencyList)
	}

	workloadSet := make(map[string]bool)
	for source, destinations := range adjacencyList {
		workloadSet[source] = true
		for _, dest := range destinations {
			workloadSet[dest] = true
		}
	}
	for _, workload := range cfg.Workload {
		workloadSet[workload] = true
	}

	// 1. Live Identity & Origin Discovery
	var prometheusVersion string
	var versionProvenance string
	var versionSource string

	if discoverer != nil {
		if ver, err := discoverer.DiscoverVersion(ctx); err == nil && ver != "" {
			prometheusVersion = ver
			versionProvenance = "observed"
			versionSource = "prometheus_build_info"
		}
	}

	if prometheusVersion == "" {
		prometheusVersion = "unknown"
		versionProvenance = "unknown"
		versionSource = "none"
	}

	// 2. Discover and Classify Metrics Semantics
	var metricNames []string
	var metadata map[string][]MetricMetadata
	var metadataErr error
	if discoverer != nil {
		metricNames, _ = discoverer.DiscoverMetricNames(ctx)
		metadata, metadataErr = discoverer.DiscoverMetadata(ctx)
	}

	// Build metrics list based on actual observed metrics and their metadata
	metricsSemantics := make([]config.MetricSemanticInfo, 0)
	temporalBehavior := make(map[string]config.TemporalBehaviorInfo)
	provenanceMap := make(map[string]config.ProvenanceEntry)

	// Keep a list of actual observed metric names
	observedMetricsMap := make(map[string]bool)
	for _, name := range metricNames {
		observedMetricsMap[name] = true
	}

	// Dynamic Metric Classification & Metadata Gathering
	for _, m := range cfg.Metrics {
		metricName := m.Name
		exists := observedMetricsMap[metricName]

		var mType, mHelp, mUnit string
		var mProv, mSource string

		if exists && metadataErr == nil && metadata != nil {
			if metaList, ok := metadata[metricName]; ok && len(metaList) > 0 {
				mType = metaList[0].Type
				mHelp = metaList[0].Help
				mUnit = metaList[0].Unit
				mProv = "observed"
				mSource = "prometheus_metadata"
			}
		}

		// Fallback to name-based inference if metadata query was unsuccessful/missing
		if mType == "" {
			if strings.HasSuffix(metricName, "_total") || strings.HasSuffix(metricName, "_count") {
				mType = "counter"
				mProv = "derived"
				mSource = "name_inference"
			} else if strings.HasSuffix(metricName, "_bucket") {
				mType = "histogram"
				mProv = "derived"
				mSource = "name_inference"
			} else {
				mType = m.Semantics.Type
				if mType == "" {
					mType = "unknown"
					mProv = "unknown"
					mSource = "none"
				} else {
					mProv = "configured"
					mSource = "ocs_config"
				}
			}
		}

		if mHelp == "" {
			mHelp = m.Semantics.Description
			if mHelp == "" {
				mHelp = "No description available."
			}
		}
		if mUnit == "" {
			mUnit = m.Semantics.Unit
		}

		metricsSemantics = append(metricsSemantics, config.MetricSemanticInfo{
			Name:        metricName,
			Type:        mType,
			Unit:        mUnit,
			Description: mHelp,
			Semantics: map[string]interface{}{
				"domain_concept": m.Semantics.DescriptiveName,
				"observed":       exists,
			},
		})

		// Temporal Behavior for this metric
		temporalBehavior[metricName] = config.TemporalBehaviorInfo{
			Mode:                mType,
			AggregationDuration: m.Temporal.GranularityResolution,
			Description:         fmt.Sprintf("Retention is %s", m.Temporal.RetentionPolicy),
		}

		provenanceMap["metrics."+metricName+".type"] = config.ProvenanceEntry{
			Value:      mType,
			Provenance: mProv,
			Source:     mSource,
		}
	}

	// 3. Temporal Context Discovery
	sampleInterval := "15s"
	retentionPolicy := "unknown"
	temporalProv := "unknown"
	temporalSource := "none"

	if discoverer != nil {
		if runtimeInfo, err := discoverer.DiscoverRuntimeInfo(ctx); err == nil && runtimeInfo != nil {
			// Try to extract retention
			if ret, ok := runtimeInfo["storageRetention"]; ok {
				retentionPolicy = fmt.Sprintf("%v", ret)
				temporalProv = "observed"
				temporalSource = "prometheus_runtime_info"
			}
		}

		if retentionPolicy == "unknown" {
			// Query retention limits metric if available
			series, err := discoverer.DiscoverSeries(ctx, "prometheus_tsdb_retention_limit_seconds")
			if err == nil && len(series) > 0 {
				retentionPolicy = "discovered_tsdb_retention"
				temporalProv = "observed"
				temporalSource = "prometheus_tsdb_retention_limit_seconds"
			}
		}
	}

	// 4. Operational Constraints Discovery
	healthConfigs := make([]config.HealthConfigConstraint, 0)
	var rulesData map[string]interface{}
	var rulesErr error
	if discoverer != nil {
		rulesData, rulesErr = discoverer.DiscoverRules(ctx)
	}

	for _, m := range cfg.Metrics {
		critVal := m.Constraints.Thresholds["critical"]
		warnVal := m.Constraints.Thresholds["warning"]
		hasConfiguredAlert := critVal > 0 || warnVal > 0

		// Check if Prometheus rules endpoint has rules for this metric
		observedAlert := false
		if rulesErr == nil && rulesData != nil {
			if groups, ok := rulesData["groups"]; ok {
				if groupList, isList := groups.([]interface{}); isList {
					for _, g := range groupList {
						if groupMap, isMap := g.(map[string]interface{}); isMap {
							if rules, ok := groupMap["rules"]; ok {
								if ruleList, isRuleList := rules.([]interface{}); isRuleList {
									for _, r := range ruleList {
										if rMap, isRMap := r.(map[string]interface{}); isRMap {
											if queryVal, exists := rMap["query"]; exists {
												if strings.Contains(fmt.Sprintf("%v", queryVal), m.Name) {
													observedAlert = true
												}
											}
										}
									}
								}
							}
						}
					}
				}
			}
		}

		var oProv string
		if observedAlert {
			oProv = "observed"
		} else if hasConfiguredAlert {
			oProv = "policy"
		} else {
			oProv = "unknown"
		}

		healthConfigs = append(healthConfigs, config.HealthConfigConstraint{
			MetricName:        m.Name,
			AggregationLogic:  m.Constraints.Aggregator,
			WarningThreshold:  warnVal,
			CriticalThreshold: critVal,
			Polarity:          m.Constraints.Polarity,
			Description:       fmt.Sprintf("Rule for %s: warning at %f, critical at %f", m.Name, warnVal, critVal),
		})

		provenanceMap["constraints."+m.Name+".critical_threshold"] = config.ProvenanceEntry{
			Value:      critVal,
			Provenance: oProv,
			Source:     "alerting_rules_or_policy",
		}
	}

	timeWindow := 30
	if cfg.TimeWindowMinutes != nil {
		timeWindow = *cfg.TimeWindowMinutes
	}

	var out []config.OCSContextDefinition
	for workload := range workloadSet {
		// Extract dependency topology relationships from static configuration & dynamic metrics
		topoRelationships := buildTopology(adjacencyList, workload)

		resolvedSearchTerm := workload
		if workload == "frontend" {
			resolvedSearchTerm = "manager-ui"
		} else if workload == "backend" {
			resolvedSearchTerm = "ollama"
		} else if workload == "db" {
			resolvedSearchTerm = "clickhouse"
		}

		// Discover dynamic Kubernetes Topology details
		var topologyProv string
		var topologySource []string
		if discoverer != nil {
			details, sources := discoverer.DiscoverTopologyDetails(ctx, resolvedSearchTerm)
			if len(sources) > 0 {
				topologyProv = "observed"
				topologySource = sources
				for k, v := range details {
					topoRelationships[k] = v
				}
			} else {
				topologyProv = "configured"
				topologySource = []string{"ocs_config"}
			}
		} else {
			topologyProv = "configured"
			topologySource = []string{"ocs_config"}
		}

		// Overlay labels and configs from YAML
		labelsCombined := make(map[string]string)
		for k, v := range cfg.DimensionalityAndTopology.LabelsTags {
			labelsCombined[k] = v
		}
		// Set correct app label mapping inside context spec based on workload
		if workload == "frontend" {
			labelsCombined["app"] = "manager-ui"
		} else if workload == "backend" {
			labelsCombined["app"] = "ollama"
		} else if workload == "db" {
			labelsCombined["app"] = "chi-clickhouse-cluster"
		}

		parentChildLinksCombined := make(map[string]interface{})
		for k, v := range cfg.DimensionalityAndTopology.ParentChildLinks {
			parentChildLinksCombined[k] = v
		}

		// Set version and identity provenance
		provenanceMap["identity.version"] = config.ProvenanceEntry{
			Value:      prometheusVersion,
			Provenance: versionProvenance,
			Source:     versionSource,
		}
		provenanceMap["dimensionality.topology"] = config.ProvenanceEntry{
			Value:      topoRelationships,
			Provenance: topologyProv,
			Source:     topologySource,
		}
		provenanceMap["temporal.retention_policy"] = config.ProvenanceEntry{
			Value:      retentionPolicy,
			Provenance: temporalProv,
			Source:     temporalSource,
		}

		// Ensure we don't output empty map values
		finalProvenanceMap := make(map[string]config.ProvenanceEntry)
		for k, v := range provenanceMap {
			finalProvenanceMap[k] = v
		}

		contextDef := config.OCSContextDefinition{
			ResourceID: fmt.Sprintf("workload-%s", workload),
			Domain:     "compute.k8s",
			IdentityAndOrigin: config.IdentityAndOrigin{
				Who: map[string]interface{}{
					"workload":       workload,
					"service":        workload,
					"provider":       cfg.IdentityAndOrigin.ProviderSource,
					"binary_version": prometheusVersion,
				},
				Where: map[string]interface{}{
					"environment": cfg.IdentityAndOrigin.Environment,
					"namespace":   cfg.IdentityAndOrigin.NamespaceDomain,
				},
			},
			DimensionalityAndTopology: config.DimensionalityAndTopology{
				NodeType: cfg.DimensionalityAndTopology.ResourceType,
				Relationships: map[string]interface{}{
					"dependencies":       topoRelationships["dependencies"],
					"dependents":         topoRelationships["dependents"],
					"parent_child_links": parentChildLinksCombined,
					"labels_tags":        labelsCombined,
					"pods":               topoRelationships["pods"],
					"nodes":              topoRelationships["nodes"],
					"namespaces":         topoRelationships["namespaces"],
					"containers":         topoRelationships["containers"],
					"pod_owners":         topoRelationships["pod_owners"],
				},
			},
			MetricSemantics: metricsSemantics,
			TemporalContext: config.TemporalContext{
				Timestamp:         "",
				TimeWindowMinutes: timeWindow,
				SampleInterval:    sampleInterval,
				TemporalBehavior:  temporalBehavior,
			},
			OperationalConstraints: config.OperationalConstraints{
				HealthConfig: healthConfigs,
				Policies:     cfg.Policy,
			},
			ProvenanceMap: finalProvenanceMap,
		}

		// Ensure the sample interval is mapped in temporal behavior
		if durSecs, err := strconv.Atoi(strings.TrimSuffix(sampleInterval, "s")); err == nil {
			contextDef.TemporalContext.SampleInterval = fmt.Sprintf("%ds", durSecs)
		}

		out = append(out, contextDef)
	}

	return out
}

func buildTopology(adjacencyList connectors.AdjacencyList, workload string) map[string]interface{} {
	topology := make(map[string]interface{})

	if destinations, exists := adjacencyList[workload]; exists && len(destinations) > 0 {
		topology["dependencies"] = destinations
	}

	var reverseDeps []string
	for source, destinations := range adjacencyList {
		for _, dest := range destinations {
			if dest == workload {
				reverseDeps = append(reverseDeps, source)
			}
		}
	}
	if len(reverseDeps) > 0 {
		topology["dependents"] = reverseDeps
	}

	return topology
}
