"""
Prometheus connector for SODA Contexture.

Provides connection helpers used by the MCP tools.
Connection settings are loaded from config/prometheus_config.yaml.
"""

import os
import yaml
from typing import Dict, List

from prometheus_api_client import PrometheusConnect


def _load_config() -> List[Dict]:
    """Load prometheus_config.yaml from the repo config directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.normpath(
        os.path.join(here, "..", "..", "..", "config", "prometheus_config.yaml")
    )

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"prometheus_config.yaml not found at {config_path}\n"
            "Make sure config/prometheus_config.yaml exists at the repo root."
        )

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    return cfg.get("prometheus_instances", [])


def get_all_instances() -> List[Dict]:
    """Return raw config dicts for all configured Prometheus instances."""
    return _load_config()


class HistoricalPrometheusConnect(PrometheusConnect):
    def custom_query(self, query: str, params: dict = None):
        if params is None:
            params = {}
        if "time" not in params:
            # Pin instant queries to the latest recorded metric timestamp in the historical database
            params["time"] = "1784722716"
        return super().custom_query(query, params)

def get_client(instance: Dict) -> PrometheusConnect:
    """Create a PrometheusConnect client for a given config instance."""
    return HistoricalPrometheusConnect(
        url=instance["base_url"],
        headers=instance.get("headers", {}),
        disable_ssl=instance.get("disable_ssl", False),
    )
