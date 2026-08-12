import asyncio
import json
import httpx
import re
import os
import yaml
import string
from fastmcp import Client
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
from pkg.cpa.agent import ContextPlanningAgent, AmbiguousQueryException

app = FastAPI(title="Contexture Backend Service")


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_config(path="config.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)

# Load configurations
config_base = os.path.join(os.path.dirname(__file__), "../../config")
ollama_config = load_config(os.path.join(config_base, "ollama_config.yaml"))
server_config = load_config(os.path.join(config_base, "mcp_server_config.yaml"))

OLLAMA_API_URL = ollama_config.get("ollama_url")
MODEL_NAME = ollama_config.get("ollama_model")
# Renamed to mcp_client to avoid shadowing by the local httpx client inside llm_to_workflow
mcp_client = Client(server_config.get("mcp_server_url", "http://localhost:8001/mcp"))

# CPA Initialization
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGO_DB = os.getenv("MONGODB_DB_NAME", "ocs")
OCS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../ocs/ocs_config_v2.yaml")

cpa = ContextPlanningAgent(
    ollama_url=OLLAMA_API_URL,
    model_name=MODEL_NAME,
    mongo_uri=MONGO_URI,
    db_name=MONGO_DB,
    ocs_config_path=OCS_CONFIG_PATH
)

def clean_and_shrink_spec(spec_dict: dict) -> dict:
    if not spec_dict:
        return spec_dict
    import copy
    cleaned = copy.deepcopy(spec_dict)
    if "context_definitions" in cleaned:
        for definition in cleaned["context_definitions"]:
            # Remove provenance map
            for pkey in ["provenance_map", "provenancemap"]:
                if pkey in definition:
                    del definition[pkey]
            
            # Truncate topology lists
            for tkey in ["dimensionality_and_topology", "dimensionalityandtopology"]:
                if tkey in definition:
                    topo = definition[tkey]
                    if "relationships" in topo and topo["relationships"]:
                        rels = topo["relationships"]
                        for key in ["containers", "nodes", "namespaces", "pod_owners", "pods"]:
                            if key in rels and isinstance(rels[key], list):
                                # Truncate lists to avoid overloading Ollama context window
                                rels[key] = rels[key][:2]
            
            # Clean temporal context
            for temp_key in ["temporal_context", "temporalcontext"]:
                if temp_key in definition:
                    temp_ctx = definition[temp_key]
                    if "timestamp" in temp_ctx:
                        del temp_ctx["timestamp"]
    return cleaned

def format_relevant_context_as_ocs_spec(relevant_context) -> dict:
    context_definitions = []
    dependencies_map = {}
    dependents_map = {}
    for rel in relevant_context.relationships:
        src_name = rel.source.replace("workload-", "")
        tgt_name = rel.target.replace("workload-", "")
        if src_name not in dependencies_map:
            dependencies_map[src_name] = []
        dependencies_map[src_name].append(tgt_name)
        if tgt_name not in dependents_map:
            dependents_map[tgt_name] = []
        dependents_map[tgt_name].append(src_name)

    for entity in relevant_context.entities:
        topology = {}
        if entity.name in dependencies_map:
            topology["dependencies"] = dependencies_map[entity.name]
        if entity.name in dependents_map:
            topology["dependents"] = dependents_map[entity.name]

        context_definitions.append({
            "resource_id": entity.id,
            "domain": entity.metadata.get("domain", "compute.k8s"),
            "identity": entity.metadata.get("identity", {"workload": entity.name}),
            "metrics": entity.metadata.get("metrics", []),
            "policy": entity.metadata.get("policy", []),
            "topology": topology
        })
    return {
        "spec_version": "0.1",
        "context_definitions": context_definitions,
        "freshness": {
            "last_collected_at": relevant_context.freshness.last_collected_at,
            "data_age_seconds": relevant_context.freshness.data_age_seconds,
            "is_stale": relevant_context.freshness.is_stale
        }
    }


# Data Models
class QueryRequest(BaseModel):
    query: str
    context: Optional[str] = ""

class QueryResponse(BaseModel):
    summary: str
    results: List[Dict]
    workflow: List[Dict]
    ocs_input: str
    ocs_output: str
    timestamp: str

async def ask_ollama_stream(prompt: str):
    async with httpx.AsyncClient(timeout=None) as session:
        async with session.stream(
            "POST",
            f"{OLLAMA_API_URL}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.0,
                "stream": True
            },
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk != "[DONE]":
                        try:
                            data = json.loads(chunk)
                            text = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if text:
                                yield text
                        except json.JSONDecodeError:
                            continue

async def ask_ollama(prompt: str, history="") -> str:
    content = prompt
    if history:
        content = f"{history}\n\n{prompt}"
    async with httpx.AsyncClient(timeout=300.0) as session:
        resp = await session.post(
            f"{OLLAMA_API_URL}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 1000,
                "temperature": 0.0
            }
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# Returns only list (ocs_prompt is fetched separately in run_query)
async def llm_to_workflow(nl_query: str) -> list:
    print("Entering llm_to_workflow with query:", nl_query)

    # Run CPA planner to extract target entities for query routing
    relevant_context, plan = await cpa.get_relevant_context(nl_query)
    target_entities = [te.name.lower() for te in plan.target_entities if hasattr(te, 'name') and te.name]

    # Fetch live 1.0.0 context definitions from MongoDB if populated
    context_defs = await cpa.get_latest_ocs_context()
    if context_defs:
        # Filter context definitions to keep only the relevant target workloads
        filtered_defs = []
        has_workload_match = False
        for d in context_defs:
            res_id = d.get("resource_id", "").lower()
            if not target_entities or "prometheus" in target_entities or "all" in target_entities:
                filtered_defs.append(d)
            else:
                matches = [te for te in target_entities if te in res_id]
                if matches:
                    filtered_defs.append(d)
                    has_workload_match = True
        
        # If we had target entities, but they were infra-specific (like 'node') and didn't match any workload,
        # do not fall back to sending all workloads. Keep filtered_defs empty to keep the prompt clean.
        if not filtered_defs and not has_workload_match:
            if not target_entities:
                filtered_defs = context_defs
            else:
                filtered_defs = []

        ocs_prompt_dict = {
            "spec_version": "1.0.0",
            "context_definitions": filtered_defs
        }
    else:
        # Fallback to legacy context from MongoDB
        ocs_prompt_dict = format_relevant_context_as_ocs_spec(relevant_context)
    ocs_prompt = json.dumps(clean_and_shrink_spec(ocs_prompt_dict))

    print("\n" + "="*60)
    print("[CPA] --- Relevant Context Output Spec for Copilot ---")
    print(json.dumps(ocs_prompt_dict, indent=2))
    print("="*60 + "\n")

    print("Fetched CPA relevant context from MongoDB")

    
    prompt = (
        "You are an assistant that converts natural language queries into a sequence of available MCP tool calls. "
        "Return ONLY JSON. Each step should include 'tool_name', 'params' (dictionary), "
        "arrange it in a logical flow of calls. Limit to a maximum of 4 calls when the user asks about full stack or all workloads (so you can cover policy + up to 3 workloads); otherwise maximum 3 calls, minimum 1 call.\n"
        "If there are params that can't be filled based on the info you have, make it empty string.\n\n"
        "Context specification from the context provider (JSON):\n"
        f"{ocs_prompt}\n\n"
        "Topology (hierarchy): Each context_definition may have a 'topology' object.\n"
        "- 'dependencies' = workloads this workload calls (downstream dependencies).\n"
        "- 'dependents' = workloads that call this workload (upstream callers).\n"
        "Example: frontend depends on backend, backend depends on db → for 'backend', dependencies=[db], dependents=[frontend].\n\n"
        "Composing workload calls:\n"
        "- When the user asks about a workload 'and its dependencies', 'stack', 'layer', 'chain', or 'and what it calls': "
        "call workload_metrics for that workload AND each of its topology.dependencies (in dependency order: leaf first, e.g. db then backend then frontend).\n"
        "- When the user asks about 'full stack', 'all layers', 'whole chain', or 'all workloads': "
        "call workload_metrics for each workload in dependency order (dependencies before dependents).\n"
        "- Use the specification's workload names and metrics; map synonyms (e.g. database, DB → db).\n\n"
        "If the user asks to explain/interpret policy (SLA, thresholds, what the policy means), include a call to explain_ocs_policy first.\n\n"
        "Available Tools:\n"
        "- explain_ocs_policy(config_path: str = 'pkg/ocs/ocs_config.yaml', output_format: str = 'bullets')\n"
        "- workload_metrics(metric_name: str = 'container_cpu_utilization', workload_name: Optional[str] = None, pod_names: Optional[List[str]] = None, time_window: Optional[str] = None, aggregation: str = 'avg')\n"
        "- top_n_pods_by_metric(metric_name: str = 'container_cpu_usage_seconds_total', top_n: int = 5, window: str = '5m')\n"
        "- pods_exceeding_cpu(threshold: float = 0.8)\n"
        "- pods_exceeding_memory(threshold_bytes: float = 1073741824)\n"
        "- pod_status_summary() (Use this when the user asks to list pods, show pod status, or list all Kubernetes pods)"
        " - NOTE: returns aggregate COUNTS only, not individual pod names\n"
        "- list_all_pods(namespace: Optional[str] = None) (Use this when the user asks to list all pods, enumerate pods, or list pod names - returns individual pod names with namespace and node)\n"
        "- node_disk_usage(window_minutes: int = 20)\n"
        "- node_memory_usage(window_minutes: int = 20)\n"
        "- describe_cluster_health()\n"
        "- top_disk_pressure_nodes(threshold: float = 80.0, top_n: int = 5)\n"
        "- top_memory_pressure_nodes(threshold: float = 80.0, top_n: int = 5)\n"
        "- pod_restart_trend(window: str = '30m', top_n: int = 5)\n"
        "- detect_pod_anomalies(metric_name='container_cpu_usage_seconds_total', z_threshold=3.0)\n"
        "- detect_crashloop_pods(window='10m', threshold=2)\n"
        "- detect_restart_anomalies(window: str = '24h', threshold: int = 2) (Use this when the user asks for restart anomalies in pods or container restart counts)\n"
        "- namespace_resource_summary(resource: str = 'cpu', window: str = '5m') (Use this when the user asks to compare development vs. production workloads, or namespace resource footprints/summaries)\n"
        "- pod_event_timeline(pod_name: str, window: str = '30m')\n"
        "- node_condition_summary()\n"
        "- query_custom_metric_range(metric_name: str, window: str = '30d') (Use this when the user asks for a specific metric name like kube_node_status_capacity_cpu_cores or any other custom raw metric over a past window)\n\n"
        f"Natural language query: {nl_query}"
    )
    llm_response = await ask_ollama(prompt)
    llm_response = llm_response.strip()
    try:
        # Regex search for JSON array
        array_match = re.search(r"\[\s*\{.*\}\s*\]", llm_response, re.DOTALL)
        if array_match:
            workflow = json.loads(array_match.group(0))
        else:
            # Try searching for JSON dict
            dict_match = re.search(r"\{\s*.*\}", llm_response, re.DOTALL)
            if dict_match:
                workflow = [json.loads(dict_match.group(0))]
            else:
                workflow = json.loads(llm_response)
        
        if not isinstance(workflow, list):
            workflow = [workflow]
        return workflow
    except Exception:
        # Smart fallback matching key terms instead of using raw query as tool name
        query_lower = nl_query.lower()
        if "pod" in query_lower:
            return [{"tool_name": "pod_status_summary", "params": {}}]
        if "memory" in query_lower:
            return [{"tool_name": "node_memory_usage", "params": {}}]
        if "disk" in query_lower:
            return [{"tool_name": "node_disk_usage", "params": {}}]
        return [{"tool_name": "describe_cluster_health", "params": {}}]


async def execute_workflow(workflow: list) -> list:
    
    context = {}  
    results = []
    history = ""

    async with mcp_client:
        for step in workflow:

            print("Executing step:", step)

            tool_name = step.get("tool_name")
            params = step.get("params", {}).copy()

            # print(params.items())
            for k, v in params.items():
                if isinstance(v, str) and "{" in v:
                    try:
                        params[k] = string.Template(v).safe_substitute(context)
                    except Exception:
                        pass

            # Collect keys that need resolution BEFORE iterating to avoid mutation errors
            keys_to_resolve = []
            for k, v in params.items():
                if v is None or (isinstance(v, str) and v.strip() == "") or v == "" or v == []:
                    keys_to_resolve.append(k)

            # If we need to resolve parameters from previous steps but no data exists, skip the step
            if keys_to_resolve and results:
                has_data = False
                for r in results:
                    r_val = r.get("result", {})
                    if isinstance(r_val, dict):
                        for val in r_val.values():
                            if isinstance(val, dict):
                                for subval in val.values():
                                    if (isinstance(subval, list) and len(subval) > 0) or (isinstance(subval, (int, float))):
                                        has_data = True
                                    elif isinstance(subval, str) and subval.strip() != "":
                                        has_data = True
                            elif (isinstance(val, list) and len(val) > 0) or isinstance(val, (int, float)):
                                has_data = True
                            elif isinstance(val, str) and val.strip() != "":
                                has_data = True
                if not has_data:
                    print(f"Skipping step {tool_name} because parent dependency results are empty.")
                    continue

            for k in keys_to_resolve:
                print("Resolving param my making another call to LLM...")
                summary_prompt = f"Summarize these tool call results: {results}\nProvide a neat minimal summary."

                llm_value = await ask_ollama(summary_prompt, "")
                prompt = (
                    f"\nGiven the previous tool outputs, \n"
                    f"Read carefully and get the appropriate value from previous tool outputs for the workflow step for parameter {k}. Make sure the value is of correct type (str, int, list etc)"
                    "and return tool call only in JSON format. remove unnecessary characters and '\n', also make sure number of params is same as the workflow step \n"
                )
                llm_value = await ask_ollama(prompt, "Workflow Step: "+str(step) + " Previous tool results: "+str(llm_value))
                try:
                    # Try parsing JSON first; update only this key, don't replace the whole params dict
                    parsed_value = re.sub(r"```(?:json)?", "", llm_value.strip())
                    resolved_params = json.loads(parsed_value)
                    params[k] = resolved_params.get("params", {}).get(k, resolved_params)
                except json.JSONDecodeError:
                    # fallback: use raw text for this key only
                    params[k] = re.sub(r"```(?:json)?", "", llm_value.strip())

           
            try:
                print("Calling tool:", tool_name, "with params:", params)
                result = await mcp_client.call_tool(tool_name, params)
            except Exception as e:
                result = {"error": str(e)}

            results.append({"tool_name": tool_name, "result": result})

    return results


async def run_query(nl_query: str) -> tuple:
    workflow = await llm_to_workflow(nl_query)
    print("Generated Workflow:", workflow)

    # Run CPA planner to extract target entities for query routing
    relevant_context, plan = await cpa.get_relevant_context(nl_query)
    target_entities = [te.name.lower() for te in plan.target_entities if hasattr(te, 'name') and te.name]

    # Fetch live 1.0.0 context definitions from MongoDB if populated
    context_defs = await cpa.get_latest_ocs_context()
    if context_defs:
        # Filter context definitions to keep only the relevant target workloads
        filtered_defs = []
        has_workload_match = False
        for d in context_defs:
            res_id = d.get("resourceid", d.get("resource_id", "")).lower()
            if not target_entities or "prometheus" in target_entities or "all" in target_entities:
                filtered_defs.append(d)
            else:
                workload = d.get("identityandorigin", {}).get("who", {}).get("workload", "").lower()
                topo = d.get("dimensionalityandtopology", d.get("dimensionality_and_topology", {}))
                rels = topo.get("relationships", {}) if isinstance(topo, dict) else {}
                pods = rels.get("pods", []) if isinstance(rels, dict) else []
                pods_str = " ".join([p.lower() for p in pods if isinstance(p, str)])
                
                matches = []
                for te in target_entities:
                    if te in res_id or te in workload or te in pods_str:
                        matches.append(te)
                if matches:
                    filtered_defs.append(d)
                    has_workload_match = True
        
        # If we had target entities, but they were infra-specific (like 'node') and didn't match any workload,
        # do not fall back to sending all workloads. Keep filtered_defs empty to keep the prompt clean.
        if not filtered_defs and not has_workload_match:
            if not target_entities:
                filtered_defs = context_defs
            else:
                filtered_defs = []

        ocs_prompt_dict = {
            "spec_version": "1.0.0",
            "context_definitions": filtered_defs
        }
    else:
        # Fallback to legacy context from MongoDB
        ocs_prompt_dict = format_relevant_context_as_ocs_spec(relevant_context)
    ocs_prompt = json.dumps(clean_and_shrink_spec(ocs_prompt_dict))
    # Truncate OCS prompt to avoid overwhelming small LLMs with huge context
    if len(ocs_prompt) > 2500:
        ocs_prompt = ocs_prompt[:2500] + "... [truncated for brevity]"


    results = await execute_workflow(workflow)

    # Format results to be clean, unescaped, and highly readable for the LLM
    def safe_extract_data(r: dict) -> str:
        """Extract the cleanest possible data payload from an MCP tool result."""
        try:
            res_data = r.get("result", {})
            # Try structured_content first (cleanest)
            data = None
            if isinstance(res_data, dict):
                data = res_data.get("structured_content") or res_data.get("data")
                if not data and "content" in res_data:
                    for c in res_data.get("content", []):
                        if isinstance(c, dict) and c.get("type") == "text":
                            try:
                                data = json.loads(c.get("text", ""))
                                break
                            except Exception:
                                data = c.get("text")
                                break
            else:
                # MCP object — try attribute access
                data = getattr(res_data, "structured_content", None) or getattr(res_data, "data", None)
                if not data:
                    content = getattr(res_data, "content", [])
                    for c in content:
                        text = getattr(c, "text", None)
                        if text:
                            try:
                                data = json.loads(text)
                            except Exception:
                                data = text
                            break
            if data is None:
                data = str(res_data)
            try:
                return json.dumps(data, indent=2, default=str)
            except Exception:
                return str(data)
        except Exception as ex:
            return f"(Could not parse result: {ex})"

    formatted_results_list = []
    for r in results:
        tool_name = r.get("tool_name", "unknown")
        formatted_results_list.append(f"Tool Executed: {tool_name}")
        formatted_results_list.append(f"Output Data:\n{safe_extract_data(r)}")
        formatted_results_list.append("-" * 40)

    clean_results_str = "\n".join(formatted_results_list)

    summary_prompt = (
        f"Analyze these tool call results:\n{clean_results_str}\n\n"
        "Provide a polished, professional diagnostic report structured with these Markdown headers:\n\n"
        "### 📊 Executive Summary\n"
        "(A clean 1-2 sentence overview of the system state and findings)\n\n"
        "### 📈 Telemetry Insights & SLA Verification\n"
        "(Format all retrieved telemetry metric values, trends, status counts, or metadata labels in a clean, highly readable bulleted list. State compliance status relative to the OCS spec if applicable. DO NOT use markdown tables or graph representations)\n\n"
        "### 🔗 Topology Diagnostics\n"
        "(Diagnostic analysis of dependencies along the workload path if topology is present in the context, showing potential root-cause directions)\n\n"
        "### 💡 Recommendations\n"
        "(Bullet points recommending next steps based strictly on findings)\n\n"
        f"Context specification: {ocs_prompt}\n\n"
        "Rules:\n"
        "- Print the actual tool results data faithfully. If the tool returned counts (like Failed: 9, Running: 138), you must print them directly under Telemetry Insights. DO NOT make up metrics or report false errors if the tool succeeded.\n"
        "- If any tool result contains an 'error' key, state clearly that the tool execution failed with that error.\n"
        "- If the tool results are completely empty (e.g. empty lists [] or empty dictionaries {}), state clearly that no telemetry data was returned by Prometheus.\n"
        "- Do not make up values; use only numbers or labels present in the telemetry results.\n"
        "- Keep descriptions concise, data-driven, and highly readable."
    )
    full_summary = ""
    async for chunk in ask_ollama_stream(summary_prompt):
        print(chunk, end="", flush=True)
        full_summary += chunk
    
    print("\n")
    
    return full_summary, results


# FastAPI Endpoints

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def root():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SODA Contexture Copilot</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@400;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            :root {
                --bg: #090b11;
                --card-bg: rgba(17, 22, 37, 0.6);
                --border: rgba(255, 255, 255, 0.08);
                --glow: rgba(99, 102, 241, 0.15);
                --primary: #6366f1;
                --primary-glow: #4f46e5;
                --text: #e2e8f0;
                --text-muted: #94a3b8;
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: flex-start;
                align-items: center;
                overflow-x: hidden;
                background-image: 
                    radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
                    radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.05) 0%, transparent 40%);
            }

            header {
                width: 100%;
                max-width: 1200px;
                padding: 2.5rem 1.5rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .logo-area {
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }

            .logo-area h1 {
                font-family: 'Space Grotesk', sans-serif;
                font-size: 1.75rem;
                font-weight: 700;
                background: linear-gradient(135deg, #6366f1, #a855f7);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: -0.05em;
            }

            .badge {
                background: rgba(99, 102, 241, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.2);
                color: #818cf8;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            main {
                width: 100%;
                max-width: 1200px;
                padding: 0 1.5rem 4rem 1.5rem;
                display: flex;
                flex-direction: column;
                gap: 2rem;
                flex-grow: 1;
            }

            .search-section {
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                border: 1px solid var(--border);
                border-radius: 24px;
                padding: 2rem;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37), inset 0 1px 0 rgba(255, 255, 255, 0.05);
                position: relative;
                overflow: hidden;
            }

            .search-section::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 3px;
                background: linear-gradient(90deg, #6366f1, #a855f7);
            }

            .search-title {
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 1rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .input-wrapper {
                display: flex;
                gap: 1rem;
                width: 100%;
            }

            input[type="text"] {
                flex-grow: 1;
                background: rgba(9, 11, 17, 0.8);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 1.25rem 1.5rem;
                font-family: inherit;
                font-size: 1.1rem;
                color: var(--text);
                outline: none;
                transition: all 0.3s ease;
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
            }

            input[type="text"]:focus {
                border-color: var(--primary);
                box-shadow: 0 0 15px var(--glow), inset 0 2px 4px rgba(0, 0, 0, 0.2);
            }

            button {
                background: linear-gradient(135deg, #6366f1, #4f46e5);
                border: none;
                border-radius: 16px;
                padding: 0 2.5rem;
                font-family: inherit;
                font-size: 1.1rem;
                font-weight: 600;
                color: white;
                cursor: pointer;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            }

            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
                background: linear-gradient(135deg, #818cf8, #6366f1);
            }

            button:active {
                transform: translateY(0);
            }

            button:disabled {
                background: #1e293b;
                color: #64748b;
                cursor: not-allowed;
                box-shadow: none;
                transform: none;
            }

            .loader-box {
                display: none;
                flex-direction: column;
                align-items: center;
                gap: 1rem;
                padding: 3rem 0;
            }

            .spinner {
                width: 48px;
                height: 48px;
                border: 4px solid rgba(99, 102, 241, 0.1);
                border-left-color: var(--primary);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                100% { transform: rotate(360deg); }
            }

            .loader-text {
                font-size: 1rem;
                color: var(--text-muted);
                animation: pulse 1.5s ease-in-out infinite alternate;
            }

            @keyframes pulse {
                0% { opacity: 0.6; }
                100% { opacity: 1; }
            }

            .result-card {
                display: none;
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                border: 1px solid var(--border);
                border-radius: 24px;
                padding: 2rem;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
                flex-direction: column;
                gap: 1.5rem;
            }

            .tabs {
                display: flex;
                border-bottom: 1px solid var(--border);
                gap: 1.5rem;
                margin-bottom: 0.5rem;
            }

            .tab-btn {
                background: none;
                border: none;
                box-shadow: none;
                padding: 0.75rem 0.5rem;
                color: var(--text-muted);
                font-weight: 500;
                font-size: 1rem;
                cursor: pointer;
                position: relative;
                transition: color 0.3s ease;
                border-radius: 0;
            }

            .tab-btn:hover {
                color: var(--text);
                transform: none;
                box-shadow: none;
            }

            .tab-btn.active {
                color: var(--primary);
                font-weight: 600;
            }

            .tab-btn.active::after {
                content: '';
                position: absolute;
                bottom: -1px;
                left: 0;
                width: 100%;
                height: 2px;
                background: var(--primary);
            }

            .tab-content {
                display: none;
                padding-top: 1rem;
                line-height: 1.7;
                font-size: 1.05rem;
            }

            .tab-content.active {
                display: block;
            }

            .tab-content h2, .tab-content h3 {
                margin: 1.5rem 0 0.75rem 0;
                font-family: 'Space Grotesk', sans-serif;
            }

            .tab-content h2:first-child, .tab-content h3:first-child {
                margin-top: 0;
            }

            .tab-content p {
                margin-bottom: 1rem;
            }

            .tab-content ul, .tab-content ol {
                margin-left: 1.5rem;
                margin-bottom: 1.5rem;
            }

            .tab-content li {
                margin-bottom: 0.5rem;
            }

            pre, code {
                font-family: 'Consolas', 'Courier New', Courier, monospace;
                background: rgba(9, 11, 17, 0.6);
                padding: 0.2rem 0.4rem;
                border-radius: 6px;
                font-size: 0.95rem;
                color: #f43f5e;
            }

            pre {
                padding: 1.25rem;
                overflow-x: auto;
                margin: 1rem 0;
                border: 1px solid var(--border);
                border-radius: 12px;
            }

            pre code {
                background: none;
                padding: 0;
                color: inherit;
            }

            .workflow-step {
                background: rgba(9, 11, 17, 0.4);
                border: 1px solid var(--border);
                padding: 1.25rem;
                border-radius: 16px;
                margin-bottom: 1rem;
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
            }

            .workflow-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .tool-badge {
                font-family: 'Consolas', monospace;
                background: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.3);
                color: #818cf8;
                padding: 0.25rem 0.5rem;
                border-radius: 6px;
                font-size: 0.9rem;
            }

            .clarification-box {
                background: rgba(245, 158, 11, 0.1);
                border: 1px solid rgba(245, 158, 11, 0.2);
                border-radius: 16px;
                padding: 1.5rem;
                color: #fbbf24;
                margin-bottom: 1.5rem;
                display: none;
            }

            .clarification-box h4 {
                margin-bottom: 0.5rem;
                font-size: 1.1rem;
                font-weight: 600;
            }
        </style>
    </head>
    <body>
        <header>
            <div class="logo-area">
                <h1>SODA CONTEXTURE</h1>
                <span class="badge">Copilot</span>
            </div>
            <div style="font-size: 0.9rem; color: var(--text-muted);">
                Target CLI logs will capture background fetches.
            </div>
        </header>

        <main>
            <section class="search-section">
                <div class="search-title">Enter Incident or Monitoring Query</div>
                <div class="input-wrapper">
                    <input type="text" id="queryInput" placeholder="e.g. Why is backend latency high?" onkeypress="handleKeyPress(event)">
                    <button id="sendBtn" onclick="sendQuery()">Analyze</button>
                </div>
            </section>

            <div id="loader" class="loader-box">
                <div class="spinner"></div>
                <div class="loader-text">CPA is Planning Context & Querying Prometheus...</div>
            </div>

            <div id="clarificationBox" class="clarification-box">
                <h4>Clarification Required</h4>
                <p id="clarificationText"></p>
            </div>

            <section id="resultCard" class="result-card">
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('summary')">Summary Analysis</button>
                    <button class="tab-btn" onclick="switchTab('workflow')">Executed Workflow</button>
                    <button class="tab-btn" onclick="switchTab('raw')">Raw Tool Output</button>
                </div>

                <div id="summaryTab" class="tab-content active"></div>

                <div id="workflowTab" class="tab-content">
                    <div id="workflowStepsList"></div>
                </div>

                <div id="rawTab" class="tab-content">
                    <pre><code class="language-json" id="rawJsonCode"></code></pre>
                </div>
            </section>
        </main>

        <script>
            function handleKeyPress(e) {
                if (e.key === 'Enter') {
                    sendQuery();
                }
            }

            function switchTab(tabName) {
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

                const clickedBtn = Array.from(document.querySelectorAll('.tab-btn')).find(btn => btn.innerText.toLowerCase().includes(tabName));
                if (clickedBtn) clickedBtn.classList.add('active');

                const targetContent = document.getElementById(tabName + 'Tab');
                if (targetContent) targetContent.classList.add('active');
            }

            async function sendQuery() {
                const queryInput = document.getElementById('queryInput');
                const query = queryInput.value.trim();
                if (!query) return;

                const sendBtn = document.getElementById('sendBtn');
                const loader = document.getElementById('loader');
                const resultCard = document.getElementById('resultCard');
                const clarificationBox = document.getElementById('clarificationBox');

                // UI Loading state
                sendBtn.disabled = true;
                queryInput.disabled = true;
                loader.style.display = 'flex';
                resultCard.style.display = 'none';
                clarificationBox.style.display = 'none';

                try {
                    const response = await fetch('/api/query', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ query: query })
                    });
                    
                    const data = await response.json();
                    
                    if (data.status === 'clarification_needed') {
                        document.getElementById('clarificationText').innerText = data.prompt;
                        clarificationBox.style.display = 'block';
                    } else if (data.status === 'success') {
                        // Render Summary Markdown
                        document.getElementById('summaryTab').innerHTML = marked.parse(data.summary || '');
                        
                        // Render Workflow Sequence
                        const workflowList = document.getElementById('workflowStepsList');
                        workflowList.innerHTML = '';
                        
                        const results = data.results || [];
                        results.forEach((res, index) => {
                            const stepDiv = document.createElement('div');
                            stepDiv.className = 'workflow-step';
                            stepDiv.innerHTML = `
                                <div class="workflow-header">
                                    <span class="tool-badge">Step ${index + 1}: ${res.tool_name}</span>
                                </div>
                                <div style="font-size: 0.95rem; margin-top: 0.5rem; word-break: break-all;">
                                    <strong>Raw Response:</strong> 
                                    <pre><code>${JSON.stringify(res.result, null, 2)}</code></pre>
                                </div>
                            `;
                            workflowList.appendChild(stepDiv);
                        });

                        // Render Raw JSON Code
                        document.getElementById('rawJsonCode').innerText = JSON.stringify(data, null, 2);

                        resultCard.style.display = 'flex';
                        switchTab('summary');
                    } else {
                        alert('Error processing query: ' + (data.detail || 'Unknown error'));
                    }
                } catch (err) {
                    alert('Network error communicating with the backend server: ' + err.message);
                } finally {
                    sendBtn.disabled = false;
                    queryInput.disabled = false;
                    loader.style.display = 'none';
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/query")
async def process_query(request: QueryRequest):
    """
    Process a natural language query and return results with OCS context
    """
    try:
        full_summary, results = await run_query(request.query)
        return {
            "status": "success",
            "summary": full_summary,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    except AmbiguousQueryException as aqe:
        return {
            "status": "clarification_needed",
            "prompt": str(aqe),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] /api/query failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config")
def get_config():
    """Return current backend configuration"""
    return {
        "ollama_url": OLLAMA_API_URL,
        "model": MODEL_NAME,
        "mcp_server": server_config.get("mcp_server_url"),
        "status": "configured"
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting Contexture Backend Service...")
    print(f"Ollama URL: {OLLAMA_API_URL}")
    print(f"Model: {MODEL_NAME}")
    print(f"MCP Server: {server_config.get('mcp_server_url')}")
    uvicorn.run(app, host="0.0.0.0", port=8002)
