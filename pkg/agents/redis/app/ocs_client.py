import os
from typing import Any, Dict

import httpx
import yaml

from app.business_context import BusinessContextLoader


def load_runtime_config() -> Dict[str, Any]:
    base_dir = os.path.abspath(__file__)
    for _ in range(5):
        base_dir = os.path.dirname(base_dir)
    config_path = os.path.join(base_dir, "config", "redis_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def runtime_config_path() -> str:
    base_dir = os.path.abspath(__file__)
    for _ in range(5):
        base_dir = os.path.dirname(base_dir)
    return os.path.join(base_dir, "config", "redis_config.yaml")


class RedisOCSClient:
    def __init__(self):
        self.config_path = runtime_config_path()
        config = load_runtime_config()
        ocs_cfg = config.get("ocs", {})
        self.base_url = os.environ.get("OCS_BASE_URL", ocs_cfg.get("base_url", "http://localhost:8000")).rstrip("/")
        self.business_context_loader = BusinessContextLoader(config, config_path=self.config_path)

    def get_redis_context(self) -> Dict[str, Any]:
        response = httpx.get(f"{self.base_url}/get_redis_context", timeout=30.0)
        response.raise_for_status()
        return self._merge_business_context(response.json())

    def collect_redis_context(self) -> Dict[str, Any]:
        domain_context = self._load_business_context()
        kwargs: Dict[str, Any] = {"timeout": 60.0}
        if domain_context:
            kwargs["json"] = {"domain_context": domain_context}
        response = httpx.post(f"{self.base_url}/collect_redis_context", **kwargs)
        response.raise_for_status()
        return response.json()

    def _load_business_context(self) -> Dict[str, Any] | None:
        return self.business_context_loader.load()

    def _merge_business_context(self, redis_context: Dict[str, Any]) -> Dict[str, Any]:
        domain_context = self._load_business_context()
        if not domain_context:
            return redis_context

        enriched = dict(redis_context)
        enriched.setdefault("database", "redis")
        if "schema" not in enriched:
            enriched["schema"] = self._schema_from_context(redis_context)
        enriched["domain_context"] = domain_context
        return enriched

    def _schema_from_context(self, redis_context: Dict[str, Any]) -> Dict[str, Any]:
        schema_fields = [
            "keyspaces",
            "patterns",
            "relationships",
            "summary",
        ]
        return {
            field: redis_context[field]
            for field in schema_fields
            if field in redis_context
        }
