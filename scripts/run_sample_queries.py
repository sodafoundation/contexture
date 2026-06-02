#!/usr/bin/env python3
"""
Run sample query sets against Contexture.

Modes:
  ocs      - HTTP + OCS context Q&A (works with ClickHouse backend on :8000)
  copilot  - Natural language → PromQL via Ollama (needs Ollama + Prometheus)
  all      - Run ocs first, then copilot if dependencies are available

Examples:
  python3 scripts/run_sample_queries.py --mode ocs
  python3 scripts/run_sample_queries.py --mode copilot --query-set test/query_sets/example1.yaml
  python3 scripts/run_sample_queries.py --mode all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OCS_URL = os.environ.get("OCS_URL", "http://localhost:8000")
DEFAULT_OUTPUT = REPO_ROOT / "test" / "output"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def http_request(base_url: str, method: str, path: str, timeout: float = 30.0) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return {"status": resp.status, "body": json.loads(body) if body else {}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        return {"status": e.code, "error": str(e), "body": body}
    except urllib.error.URLError as e:
        return {"status": 0, "error": str(e), "body": {}}


def answer_ocs_question(text: str, ocs_payload: dict) -> str:
    """Answer simple questions using GET /get_ocs_prompt JSON (no LLM)."""
    defs_ = ocs_payload.get("context_definitions") or []
    workloads = {
        (d.get("identity") or {}).get("workload"): d for d in defs_ if d.get("identity")
    }
    lower = text.lower()

    if "list" in lower and "workload" in lower:
        lines = []
        for w, d in sorted(workloads.items()):
            dom = d.get("domain", "n/a")
            lines.append(f"- {w} (domain: {dom})")
        return "Configured workloads:\n" + ("\n".join(lines) if lines else "(none)")

    for name, d in workloads.items():
        if name and name.lower() in lower:
            topo = d.get("topology") or {}
            deps = topo.get("dependencies") or []
            dependents = topo.get("dependents") or []
            if "depend" in lower or "topology" in lower:
                return (
                    f"Workload '{name}':\n"
                    f"  dependencies: {deps}\n"
                    f"  dependents: {dependents}"
                )

    if "cpu" in lower or "metric" in lower or "policy" in lower or "sla" in lower:
        parts = []
        for w, d in sorted(workloads.items()):
            metrics = d.get("metrics") or []
            policies = d.get("policy") or []
            if metrics:
                m = metrics[0]
                name = m.get("Name") or m.get("name")
                hc = m.get("HealthConfig") or m.get("health_config") or {}
                parts.append(
                    f"- {w}: metric={name}, critical_threshold={hc.get('critical_threshold')}, "
                    f"polarity={hc.get('polarity')}"
                )
            if policies:
                parts.append(f"  policies: {policies}")
        return "Metrics and policies:\n" + ("\n".join(parts) if parts else "(none in config)")

    return (
        "Could not parse this question automatically. "
        f"Available workloads: {list(workloads.keys())}. "
        "Try asking about a specific workload's dependencies or CPU policy."
    )


def run_ocs_queries(query_set_path: Path, base_url: str) -> dict:
    data = load_yaml(query_set_path)
    results: dict[str, Any] = {}
    ocs_context: dict | None = None

    for item in data.get("queries", []):
        name = item.get("name") or item.get("text", "unnamed")
        qtype = item.get("type", "http_get")

        print(f"\n--- [{name}] ({qtype}) ---")

        if qtype == "http_get":
            path = item["path"]
            out = http_request(base_url, "GET", path)
            results[name] = out
            if path == "/get_ocs_prompt" and out.get("status") == 200:
                ocs_context = out.get("body")
            print(json.dumps(out.get("body"), indent=2)[:2000])

        elif qtype == "http_post":
            path = item["path"]
            out = http_request(base_url, "POST", path)
            results[name] = out
            print(json.dumps(out.get("body"), indent=2)[:2000])

        elif qtype == "ocs_question":
            if ocs_context is None:
                prep = http_request(base_url, "POST", "/collect_topology")
                ctx = http_request(base_url, "GET", "/get_ocs_prompt")
                if ctx.get("status") != 200:
                    results[name] = {"error": "get_ocs_prompt failed", "detail": ctx}
                    print(results[name])
                    continue
                ocs_context = ctx.get("body")
                results["_collect_topology"] = prep

            text = item.get("text", "")
            answer = answer_ocs_question(text, ocs_context)
            results[name] = {"question": text, "answer": answer}
            print(f"Q: {text}\nA: {answer}")

        else:
            results[name] = {"error": f"unknown type: {qtype}"}
            print(results[name])

    return results


def check_url(url: str, path: str = "") -> bool:
    try:
        full = f"{url.rstrip('/')}{path}"
        with urllib.request.urlopen(full, timeout=3) as r:
            return r.status < 500
    except Exception:
        return False


def run_copilot_queries(
    query_set_path: Path,
    prom_config_path: Path,
    copilot_module: str,
    output_dir: Path,
) -> None:
    sys.path.insert(0, str(REPO_ROOT))
    from pkg.workflows.run_queries import run_workflow

    run_workflow(
        query_set_path=str(query_set_path),
        prom_config_path=str(prom_config_path),
        copilot_mode_module=copilot_module,
        output_dir=str(output_dir),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Contexture sample queries")
    parser.add_argument(
        "--mode",
        choices=["ocs", "copilot", "all"],
        default="ocs",
        help="ocs=ClickHouse/OCS API (default), copilot=Ollama+Prometheus, all=both",
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="",
        help="YAML query set path (default depends on mode)",
    )
    parser.add_argument("--ocs-url", default=DEFAULT_OCS_URL)
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help="Directory for result YAML files",
    )
    parser.add_argument(
        "--prometheus-config",
        default=str(REPO_ROOT / "config" / "prometheus_config.yaml"),
    )
    parser.add_argument("--copilot", default="DYNAMIC_PROMPT")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.mode in ("ocs", "all"):
        ocs_set = Path(args.query_set) if args.query_set and args.mode == "ocs" else (
            REPO_ROOT / "test" / "query_sets" / "ocs_samples.yaml"
        )
        if not ocs_set.is_absolute():
            ocs_set = REPO_ROOT / ocs_set

        print(f"[OCS] Query set: {ocs_set}")
        print(f"[OCS] Server: {args.ocs_url}")

        if not check_url(args.ocs_url, "/health"):
            print(
                f"[ERROR] OCS server not reachable at {args.ocs_url}\n"
                "Start it with:\n"
                "  export CONNECTOR=clickhouse MONGODB_URI=memory\n"
                "  ./ocs-server"
            )
            return 1

        results = run_ocs_queries(ocs_set, args.ocs_url)
        out_file = output_dir / f"ocs_samples_{ts}.yaml"
        out_file.write_text(yaml.dump({"mode": "ocs", "results": results}, default_flow_style=False))
        print(f"\n[OCS] Results saved to {out_file}")

    if args.mode in ("copilot", "all"):
        copilot_sets = []
        if args.query_set and args.mode == "copilot":
            copilot_sets = [Path(args.query_set)]
        else:
            copilot_sets = [
                REPO_ROOT / "test" / "query_sets" / "example1.yaml",
                REPO_ROOT / "test" / "query_sets" / "example2.yaml",
            ]

        ollama_cfg = load_yaml(REPO_ROOT / "config" / "ollama_config.yaml")
        ollama_url = ollama_cfg.get("ollama_url", "").replace("[IP_ADDRESS]", "localhost")

        prom_ok = check_url("http://localhost:9090", "/-/healthy")
        ollama_ok = check_url(ollama_url.split("/api")[0], "/api/tags") or check_url(
            "http://localhost:11434", "/api/tags"
        )

        if not prom_ok or not ollama_ok:
            print(
                "\n[COPILOT] Skipped — missing dependencies:\n"
                f"  Prometheus (localhost:9090): {'OK' if prom_ok else 'NOT RUNNING'}\n"
                f"  Ollama ({ollama_url}): {'OK' if ollama_ok else 'NOT RUNNING'}\n"
                "To run copilot sample queries:\n"
                "  1. Start Prometheus on :9090 with metrics\n"
                "  2. Start Ollama and pull the model in config/ollama_config.yaml\n"
                "  3. pip install -r requirements.txt\n"
                "  4. python3 scripts/run_sample_queries.py --mode copilot\n"
            )
            if args.mode == "copilot":
                return 1
        else:
            modes = load_yaml(REPO_ROOT / "config" / "agent_modes.yaml")
            copilot_modules = {m["name"]: m["module"] for m in modes["modes"]}
            module = copilot_modules.get(args.copilot)
            if not module:
                print(f"[ERROR] Unknown copilot {args.copilot}")
                return 1

            for qset in copilot_sets:
                print(f"\n[COPILOT] Running {qset.name} ...")
                run_copilot_queries(
                    qset,
                    Path(args.prometheus_config),
                    module,
                    output_dir,
                )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
