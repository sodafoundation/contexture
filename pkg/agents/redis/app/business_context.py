import json
import os
from typing import Any, Dict, List, Optional

import yaml


SUPPORTED_EXTENSIONS = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "txt",
}


class BusinessContextLoader:
    def __init__(self, config: Dict[str, Any], config_path: Optional[str] = None):
        business_cfg = config.get("business_context", {})
        if not isinstance(business_cfg, dict):
            business_cfg = {}
        self.enabled = True
        self.path = business_cfg.get("path") or "./business_context/ecommerce.yaml"
        self.config_path = config_path

    def load(self) -> Optional[Dict[str, Any]]:
        resolved_path = self._resolve_path(str(self.path))
        extension = os.path.splitext(resolved_path)[1].lower()
        context_format = SUPPORTED_EXTENSIONS.get(extension)
        if not context_format:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise ValueError(f"Unsupported business context format '{extension}'. Supported formats: {supported}")

        with open(resolved_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        if context_format == "json":
            content = json.loads(raw_text)
        elif context_format == "yaml":
            content = yaml.safe_load(raw_text) or {}
        else:
            content = {"documentation": raw_text}

        return {
            "enabled": True,
            "source": self.path,
            "format": context_format,
            "content": content,
        }

    def _resolve_path(self, configured_path: str) -> str:
        candidates = self._candidate_paths(configured_path)
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        raise FileNotFoundError(f"Business context file not found: {configured_path}")

    def _candidate_paths(self, configured_path: str) -> List[str]:
        if os.path.isabs(configured_path):
            return [configured_path]

        candidates = [os.path.abspath(configured_path)]

        if self.config_path:
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            candidates.append(os.path.abspath(os.path.join(config_dir, configured_path)))

        repo_root = self._repo_root()
        candidates.append(os.path.abspath(os.path.join(repo_root, configured_path)))

        redis_agent_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.abspath(os.path.join(redis_agent_root, configured_path)))

        unique_candidates: List[str] = []
        for candidate in candidates:
            if candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates

    @staticmethod
    def _repo_root() -> str:
        base_dir = os.path.abspath(__file__)
        for _ in range(5):
            base_dir = os.path.dirname(base_dir)
        return base_dir
