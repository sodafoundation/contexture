package config

// MetricSemanticsConfig represents semantic config for a metric
type MetricSemanticsConfig struct {
	DescriptiveName string `yaml:"descriptive_name"`
	Unit            string `yaml:"unit"`
	Type            string `yaml:"type"`
	Description     string `yaml:"description"`
}

// MetricTemporalConfig represents temporal config for a metric
type MetricTemporalConfig struct {
	GranularityResolution string `yaml:"granularity_resolution"`
	RetentionPolicy       string `yaml:"retention_policy"`
}

// MetricConstraintsConfig represents constraints config for a metric
type MetricConstraintsConfig struct {
	Thresholds map[string]float64 `yaml:"thresholds"`
	Polarity   string             `yaml:"polarity"`
	Aggregator string             `yaml:"aggregator"`
}

// MetricConfigV2 represents a metric configuration block
type MetricConfigV2 struct {
	Name        string                  `yaml:"name"`
	Semantics   MetricSemanticsConfig   `yaml:"semantics"`
	Temporal    MetricTemporalConfig    `yaml:"temporal"`
	Constraints MetricConstraintsConfig `yaml:"constraints"`
}

// IdentityAndOriginConfig represents structural identity mappings
type IdentityAndOriginConfig struct {
	ProviderSource  string `yaml:"provider_source"`
	Environment     string `yaml:"environment"`
	NamespaceDomain string `yaml:"namespace_domain"`
}

// TopologyConfig represents structural topology mapping config
type TopologyConfig struct {
	ResourceType     string                 `yaml:"resource_type"`
	ParentChildLinks map[string]interface{} `yaml:"parent_child_links"`
	LabelsTags       map[string]string      `yaml:"labels_tags"`
}

// OCSConfig represents the OCS configuration structure loaded from ocs_config_v2.yaml
type OCSConfig struct {
	IdentityAndOrigin        IdentityAndOriginConfig `yaml:"identity_and_origin"`
	DimensionalityAndTopology TopologyConfig          `yaml:"dimensionality_and_topology"`
	Metrics                  []MetricConfigV2        `yaml:"metrics"`
	Workload                 []string                `yaml:"workload"`
	TimeWindowMinutes        *int                    `yaml:"time_window_minutes"`
	Policy                   []string                `yaml:"policy"`
}

// PrometheusConfig represents Prometheus configuration
type PrometheusConfig struct {
	PrometheusInstances []struct {
		Name       string            `yaml:"name"`
		BaseURL    string            `yaml:"base_url"`
		Headers    map[string]string `yaml:"headers"`
		DisableSSL bool              `yaml:"disable_ssl"`
	} `yaml:"prometheus_instances"`
}

// IdentityAndOrigin represents the OCS Identity & Origin dimension
type IdentityAndOrigin struct {
	Who   map[string]interface{} `json:"who" bson:"who"`
	Where map[string]interface{} `json:"where" bson:"where"`
}

// DimensionalityAndTopology represents the OCS Dimensionality & Topology dimension
type DimensionalityAndTopology struct {
	NodeType      string                 `json:"nodetype" bson:"nodetype"`
	Relationships map[string]interface{} `json:"relationships" bson:"relationships"`
}

// MetricSemanticInfo represents the OCS Metric Semantics dimension
type MetricSemanticInfo struct {
	Name        string                 `json:"name" bson:"name"`
	Type        string                 `json:"type" bson:"type"`
	Unit        string                 `json:"unit" bson:"unit"`
	Description string                 `json:"description" bson:"description"`
	Semantics   map[string]interface{} `json:"semantics,omitempty" bson:"semantics,omitempty"`
}

// TemporalBehaviorInfo represents temporal logic/aggregations for a specific metric
type TemporalBehaviorInfo struct {
	Mode                string `json:"mode" bson:"mode"`
	AggregationDuration string `json:"aggregation_duration,omitempty" bson:"aggregation_duration,omitempty"`
	Description         string `json:"description,omitempty" bson:"description,omitempty"`
}

// TemporalContext represents the OCS Temporal Context dimension
type TemporalContext struct {
	Timestamp         string                          `json:"timestamp,omitempty" bson:"timestamp,omitempty"`
	TimeWindowMinutes int                             `json:"timewindowminutes" bson:"timewindowminutes"`
	SampleInterval    string                          `json:"sampleinterval,omitempty" bson:"sampleinterval,omitempty"`
	TemporalBehavior  map[string]TemporalBehaviorInfo `json:"temporalbehavior,omitempty" bson:"temporalbehavior,omitempty"`
}

// HealthConfigConstraint represents health thresholds/interpretation rules
type HealthConfigConstraint struct {
	MetricName        string                 `json:"metricname" bson:"metricname"`
	AggregationLogic  string                 `json:"aggregationlogic,omitempty" bson:"aggregationlogic,omitempty"`
	WarningThreshold  float64                `json:"warningthreshold,omitempty" bson:"warningthreshold,omitempty"`
	CriticalThreshold float64                `json:"criticalthreshold,omitempty" bson:"criticalthreshold,omitempty"`
	Polarity          string                 `json:"polarity,omitempty" bson:"polarity,omitempty"`
	ContextCriteria   map[string]interface{} `json:"contextcriteria,omitempty" bson:"contextcriteria,omitempty"`
	Description       string                 `json:"description,omitempty" bson:"description,omitempty"`
}

// OperationalConstraints represents the OCS Operational Constraints dimension
type OperationalConstraints struct {
	HealthConfig []HealthConfigConstraint `json:"healthconfig,omitempty" bson:"healthconfig,omitempty"`
	Policies     []string                 `json:"policies,omitempty" bson:"policies,omitempty"`
}

// ProvenanceEntry captures the lineage of a context fact
type ProvenanceEntry struct {
	Value      interface{} `json:"value,omitempty" bson:"value,omitempty"`
	Provenance string      `json:"provenance" bson:"provenance"` // observed, derived, configured, policy, unknown
	Source     interface{} `json:"source,omitempty" bson:"source,omitempty"`     // e.g. string or []string
}

// OCSContextDefinition represents a context definition in the OCS prompt response
type OCSContextDefinition struct {
	ResourceID                string                     `json:"resourceid" bson:"resourceid"`
	Domain                    string                     `json:"domain" bson:"domain"`
	IdentityAndOrigin         IdentityAndOrigin          `json:"identityandorigin" bson:"identityandorigin"`
	DimensionalityAndTopology DimensionalityAndTopology  `json:"dimensionalityandtopology" bson:"dimensionalityandtopology"`
	MetricSemantics           []MetricSemanticInfo       `json:"metricsemantics" bson:"metricsemantics"`
	TemporalContext           TemporalContext            `json:"temporalcontext" bson:"temporalcontext"`
	OperationalConstraints    OperationalConstraints     `json:"operationalconstraints" bson:"operationalconstraints"`
	ProvenanceMap             map[string]ProvenanceEntry `json:"provenance_map,omitempty" bson:"provenance_map,omitempty"`
}

// OCSPromptResponse represents the OCS prompt response structure
type OCSPromptResponse struct {
	SpecVersion        string                 `json:"spec_version" bson:"spec_version"`
	ContextDefinitions []OCSContextDefinition `json:"context_definitions" bson:"context_definitions"`
}

