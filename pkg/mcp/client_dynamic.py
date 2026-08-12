import asyncio
import json
import httpx
import re
import os
import yaml
import string
from fastmcp import Client

def load_config(path="config.yaml"):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)

ollama_config = load_config("../../config/ollama_config.yaml")
server_config  = load_config("../../config/mcp_server_config.yaml")

OLLAMA_API_URL = ollama_config.get("ollama_url")
MODEL_NAME = ollama_config.get("ollama_model")
client = Client(server_config.get("mcp_server_url", "http://localhost:8001/mcp"))

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


async def llm_to_workflow(nl_query: str) -> list:
    #print("Entering llm_to_workflow with query:", nl_query)
    global ocs_prompt

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("http://localhost:8000/get_ocs_prompt")
        resp.raise_for_status()
        ocs_prompt = resp.text   # Use the global ocs_prompt

    print("Fetched OCS context from the context provider")
    # print("OCS Prompt:", ocs_prompt)


    
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
        "- pod_status_summary() (Use this when the user asks to list pods, show pod status, or list all Kubernetes pods)\n"
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
    #print(llm_response)
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

    async with client:
        for step in workflow:

            #print("Executing step:", step)

            tool_name = step.get("tool_name")
            params = step.get("params", {}).copy()

            
            #print(params.items())
            for k, v in params.items():
                if isinstance(v, str) and "{" in v:
                    try:
                        params[k] = string.Template(v).safe_substitute(context)
                    except Exception:
                        pass

            
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
                        f"Read carefully and get the appropriate value from previous tool outputs for the workflow step for parameter {v}. Make sure the value is of correct type (str, int, list etc)"
                        "and return tool call only in JSON format. remove unnecessary characters and '\n', also make sure number of params is same as the workflow step \n"
                    )
                    llm_value = await ask_ollama(prompt, "Workflow Step: "+str(step) + " Previous tool results: "+str(llm_value))
                    try:
                        # Try parsing JSON first
                        parsed_value = re.sub(r"```(?:json)?", "", llm_value.strip())
                        params = json.loads(parsed_value)
                        params = params["params"]
                    except json.JSONDecodeError:
                        # fallback: use raw text
                        params = re.sub(r"```(?:json)?", "", llm_value.strip())
                        params = params["params"]

           
            try:
                #print("Calling tool:", tool_name, "with params:", params)
                result = await client.call_tool(tool_name, params)
            except Exception as e:
                result = {"error": str(e)}

            

            results.append({"tool_name": tool_name, "result": result})

    return results


async def run_query(nl_query: str):
    workflow = await llm_to_workflow(nl_query)
    #print("Generated Workflow:", workflow)

    results = await execute_workflow(workflow)
    #print("\nTool call results:")
    """for r in results:
        print(r)"""

    #print("OCS Prompt:", ocs_prompt)
    summary_prompt = (
        f"Summarize these tool call results: {results}\n"
        "Provide a neat minimal summary. Interpret using the context specification and its topology.\n"
        f"Context specification: {ocs_prompt}\n\n"
        "Rules:\n"
        "- Do NOT include sections for 'SLA Violations' or 'Topology Interpretation' in your output.\n"
        "- Do not assume values; analyse strictly with respect to the context specification."
    )
    full_summary = ""
    async for chunk in ask_ollama_stream(summary_prompt):
        print(chunk, end="", flush=True)
        full_summary += chunk
    print("\n")
    return full_summary, results


if __name__ == "__main__":
    global ocs_prompt
    ocs_prompt = ""
    context = ""
    while True:
        #print("\nCurrent Context:", context)
        query = str(input("\nEnter your query (or 'exit' to quit)(or 'clear' to clear your history): "))
        if query.lower() == "exit":
            break
        if query.lower() == "clear":
            context = ""
            continue

        summary, result = asyncio.run(run_query(context + query))
        context+=summary