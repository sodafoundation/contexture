package prompt

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// DiscoveryCache is a thread-safe cache with a configurable TTL
type DiscoveryCache struct {
	mu         sync.RWMutex
	data       map[string]interface{}
	expiry     map[string]time.Time
	defaultTTL time.Duration
}

// NewDiscoveryCache initializes a DiscoveryCache
func NewDiscoveryCache(defaultTTL time.Duration) *DiscoveryCache {
	return &DiscoveryCache{
		data:       make(map[string]interface{}),
		expiry:     make(map[string]time.Time),
		defaultTTL: defaultTTL,
	}
}

// Get retrieves a key from cache if it has not expired
func (c *DiscoveryCache) Get(key string) (interface{}, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	val, ok := c.data[key]
	if !ok {
		return nil, false
	}
	exp, ok := c.expiry[key]
	if ok && time.Now().After(exp) {
		return nil, false
	}
	return val, true
}

// Set saves a key-value pair to the cache
func (c *DiscoveryCache) Set(key string, val interface{}) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.data[key] = val
	c.expiry[key] = time.Now().Add(c.defaultTTL)
}

// Target represents Prometheus scrape target information
type Target struct {
	ScrapeURL string            `json:"scrapeUrl"`
	Labels    map[string]string `json:"labels"`
	Health    string            `json:"health"`
}

// MetricMetadata represents Prometheus metric metadata from /api/v1/metadata
type MetricMetadata struct {
	Type string `json:"type"`
	Help string `json:"help"`
	Unit string `json:"unit"`
}

// PrometheusDiscoverer handles active queries to discover telemetry environment details
type PrometheusDiscoverer struct {
	url    string
	client *http.Client
	cache  *DiscoveryCache
}

// NewPrometheusDiscoverer creates a discoverer instance
func NewPrometheusDiscoverer(prometheusURL string) *PrometheusDiscoverer {
	return &PrometheusDiscoverer{
		url:    prometheusURL,
		client: &http.Client{Timeout: 10 * time.Second},
		cache:  NewDiscoveryCache(5 * time.Minute),
	}
}

func (d *PrometheusDiscoverer) queryAPI(ctx context.Context, endpoint string, result interface{}) error {
	if d.url == "" {
		return fmt.Errorf("prometheus url is empty")
	}

	fullURL := fmt.Sprintf("%s%s", strings.TrimSuffix(d.url, "/"), endpoint)
	req, err := http.NewRequestWithContext(ctx, "GET", fullURL, nil)
	if err != nil {
		return err
	}

	resp, err := d.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("endpoint returned status %d: %s", resp.StatusCode, string(body))
	}

	return json.NewDecoder(resp.Body).Decode(result)
}

// DiscoverVersion extracts the Prometheus server version
func (d *PrometheusDiscoverer) DiscoverVersion(ctx context.Context) (string, error) {
	if val, ok := d.cache.Get("version"); ok {
		return val.(string), nil
	}

	var res struct {
		Status string `json:"status"`
		Data   struct {
			Result []struct {
				Metric map[string]string `json:"metric"`
			} `json:"result"`
		} `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/query?query=prometheus_build_info", &res)
	if err != nil {
		return "", err
	}

	if res.Status == "success" && len(res.Data.Result) > 0 {
		version := res.Data.Result[0].Metric["version"]
		if version != "" {
			d.cache.Set("version", version)
			return version, nil
		}
	}
	return "", fmt.Errorf("version label not found in build info")
}

// DiscoverMetricNames returns all metric names in Prometheus
func (d *PrometheusDiscoverer) DiscoverMetricNames(ctx context.Context) ([]string, error) {
	if val, ok := d.cache.Get("metric_names"); ok {
		return val.([]string), nil
	}

	var res struct {
		Status string   `json:"status"`
		Data   []string `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/label/__name__/values", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("metric_names", res.Data)
	return res.Data, nil
}

// DiscoverMetadata fetches metric metadata from /api/v1/metadata
func (d *PrometheusDiscoverer) DiscoverMetadata(ctx context.Context) (map[string][]MetricMetadata, error) {
	if val, ok := d.cache.Get("metadata"); ok {
		return val.(map[string][]MetricMetadata), nil
	}

	var res struct {
		Status string                       `json:"status"`
		Data   map[string][]MetricMetadata  `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/metadata", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("metadata", res.Data)
	return res.Data, nil
}

// DiscoverTargets queries the scrape targets
func (d *PrometheusDiscoverer) DiscoverTargets(ctx context.Context) ([]Target, error) {
	if val, ok := d.cache.Get("targets"); ok {
		return val.([]Target), nil
	}

	var res struct {
		Status string `json:"status"`
		Data   struct {
			ActiveTargets []Target `json:"activeTargets"`
		} `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/targets", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("targets", res.Data.ActiveTargets)
	return res.Data.ActiveTargets, nil
}

// DiscoverRuntimeInfo retrieves Prometheus runtime telemetry parameters
func (d *PrometheusDiscoverer) DiscoverRuntimeInfo(ctx context.Context) (map[string]interface{}, error) {
	if val, ok := d.cache.Get("runtime_info"); ok {
		return val.(map[string]interface{}), nil
	}

	var res struct {
		Status string                 `json:"status"`
		Data   map[string]interface{} `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/status/runtimeinfo", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("runtime_info", res.Data)
	return res.Data, nil
}

// DiscoverConfig retrieves Prometheus YAML config
func (d *PrometheusDiscoverer) DiscoverConfig(ctx context.Context) (map[string]interface{}, error) {
	if val, ok := d.cache.Get("config"); ok {
		return val.(map[string]interface{}), nil
	}

	var res struct {
		Status string                 `json:"status"`
		Data   map[string]interface{} `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/status/config", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("config", res.Data)
	return res.Data, nil
}

// DiscoverRules retrieves active alerting rules
func (d *PrometheusDiscoverer) DiscoverRules(ctx context.Context) (map[string]interface{}, error) {
	if val, ok := d.cache.Get("rules"); ok {
		return val.(map[string]interface{}), nil
	}

	var res struct {
		Status string                 `json:"status"`
		Data   map[string]interface{} `json:"data"`
	}

	err := d.queryAPI(ctx, "/api/v1/rules", &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set("rules", res.Data)
	return res.Data, nil
}

// DiscoverSeries queries active metric series matching a query
func (d *PrometheusDiscoverer) DiscoverSeries(ctx context.Context, match string) ([]map[string]string, error) {
	cacheKey := "series_" + match
	if val, ok := d.cache.Get(cacheKey); ok {
		return val.([]map[string]string), nil
	}

	endpoint := fmt.Sprintf("/api/v1/series?match[]=%s", url.QueryEscape(match))
	var res struct {
		Status string              `json:"status"`
		Data   []map[string]string `json:"data"`
	}

	err := d.queryAPI(ctx, endpoint, &res)
	if err != nil {
		return nil, err
	}

	d.cache.Set(cacheKey, res.Data)
	return res.Data, nil
}

// DiscoverTopologyDetails dynamically extracts topological relationships using specific metric families
func (d *PrometheusDiscoverer) DiscoverTopologyDetails(ctx context.Context, workload string) (map[string]interface{}, []string) {
	relationships := make(map[string]interface{})
	var observedSources []string

	// Target Pod -> Node and Pod -> Namespace mapping via kube_pod_info
	podInfoSeries, err := d.DiscoverSeries(ctx, fmt.Sprintf("kube_pod_info{pod=~\".*%s.*\"}", workload))
	if err == nil && len(podInfoSeries) > 0 {
		pods := make(map[string]bool)
		nodes := make(map[string]bool)
		namespaces := make(map[string]bool)

		for _, item := range podInfoSeries {
			if pod, ok := item["pod"]; ok && pod != "" {
				pods[pod] = true
			}
			if node, ok := item["node"]; ok && node != "" {
				nodes[node] = true
			}
			if ns, ok := item["namespace"]; ok && ns != "" {
				namespaces[ns] = true
			}
		}

		if len(pods) > 0 {
			podList := make([]string, 0, len(pods))
			for p := range pods {
				podList = append(podList, p)
			}
			relationships["pods"] = podList
			observedSources = append(observedSources, "kube_pod_info")
		}
		if len(nodes) > 0 {
			nodeList := make([]string, 0, len(nodes))
			for n := range nodes {
				nodeList = append(nodeList, n)
			}
			relationships["nodes"] = nodeList
		}
		if len(namespaces) > 0 {
			nsList := make([]string, 0, len(namespaces))
			for ns := range namespaces {
				nsList = append(nsList, ns)
			}
			relationships["namespaces"] = nsList
		}
	}

	// Target Container mappings via container_cpu_usage_seconds_total
	containerSeries, err := d.DiscoverSeries(ctx, fmt.Sprintf("container_cpu_usage_seconds_total{pod=~\".*%s.*\"}", workload))
	if err == nil && len(containerSeries) > 0 {
		containers := make(map[string]bool)
		for _, item := range containerSeries {
			if c, ok := item["container"]; ok && c != "" && c != "POD" {
				containers[c] = true
			}
		}
		if len(containers) > 0 {
			cList := make([]string, 0, len(containers))
			for c := range containers {
				cList = append(cList, c)
			}
			relationships["containers"] = cList
			observedSources = append(observedSources, "container_cpu_usage_seconds_total")
		}
	}

	// Discover PV -> PVC -> Pod mapping with strict evidence checks
	pvcSeries, err := d.DiscoverSeries(ctx, fmt.Sprintf("kube_pod_spec_volumes_persistentvolumeclaims_info{pod=~\".*%s.*\"}", workload))
	if err == nil && len(pvcSeries) > 0 {
		pvcToVolumeMap := make([]map[string]string, 0)
		for _, pvcItem := range pvcSeries {
			pvcName := pvcItem["persistentvolumeclaim"]
			podName := pvcItem["pod"]

			if pvcName != "" && podName != "" {
				// Query specific PV details only for this discovered PVC to link them
				pvSeries, err := d.DiscoverSeries(ctx, fmt.Sprintf("kube_persistentvolumeclaim_info{persistentvolumeclaim=\"%s\"}", pvcName))
				if err == nil && len(pvSeries) > 0 {
					for _, pvItem := range pvSeries {
						volume := pvItem["volumename"]
						if volume != "" {
							pvcToVolumeMap = append(pvcToVolumeMap, map[string]string{
								"pod":                   podName,
								"persistentvolumeclaim": pvcName,
								"persistentvolume":      volume,
							})
						}
					}
				}
			}
		}
		if len(pvcToVolumeMap) > 0 {
			relationships["persistent_volumes"] = pvcToVolumeMap
			observedSources = append(observedSources, "kube_pod_spec_volumes_persistentvolumeclaims_info+kube_persistentvolumeclaim_info")
		}
	}

	// Discover ReplicaSet/Deployment owner relations via kube_pod_owner
	ownerSeries, err := d.DiscoverSeries(ctx, fmt.Sprintf("kube_pod_owner{pod=~\".*%s.*\"}", workload))
	if err == nil && len(ownerSeries) > 0 {
		owners := make([]map[string]string, 0)
		for _, o := range ownerSeries {
			ownerInfo := map[string]string{
				"pod":        o["pod"],
				"owner_name": o["owner_name"],
				"owner_kind": o["owner_kind"],
			}
			owners = append(owners, ownerInfo)
		}
		relationships["pod_owners"] = owners
		observedSources = append(observedSources, "kube_pod_owner")
	}

	return relationships, observedSources
}
