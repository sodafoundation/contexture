import httpx
import re
import logging
import yaml
from prometheus_api_client import PrometheusConnect
from pathlib import Path


# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load Ollama config
def load_ollama_config(path="config/ollama_config.yaml"):
    if not Path(path).exists():
        raise FileNotFoundError(f"Ollama config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)
    
def enhanced_prompt_builder(user_prompt):
    from pkg.copilot.DP_logic.DynamicPrompt.dynamic_prompt.prompt_builder import PromptBuilder
    from pkg.copilot.DP_logic.DynamicPrompt.dynamic_prompt.retriever import Retriever

    question = user_prompt.strip()
    context = Retriever().query(question)

    prompt = PromptBuilder() \
        .with_context(context) \
        .with_user_question(question) \
        .with_overrides() \
        .with_golden_examples() \
        .with_additional_info() \
        .build()

    return prompt

OLLAMA_CONFIG = load_ollama_config()
OLLAMA_URL = OLLAMA_CONFIG.get("ollama_url", "http://localhost:11434/api/generate")
OLLAMA_MODEL = OLLAMA_CONFIG.get("ollama_model", "mistral")

PROMQL_PATTERN = r"```(?:promql)?\s*(.*?)\s*```"

# STEP 1: Ask Ollama to convert NL → PromQL
def get_promql_from_ollama(question: str) -> tuple:
    enhanced_prompt = enhanced_prompt_builder(question)
    
    logger.info(f"Sending Query to Ollama: {enhanced_prompt}")

    try:
        response = httpx.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": enhanced_prompt,
            "stream": False
        }, timeout=120)
    except Exception as e:
        logger.error(f"Failed to connect to Ollama: {e}")
        raise

    if response.status_code != 200:
        logger.error(f"Ollama failed: {response.status_code} - {response.text}")
        raise RuntimeError(f"Ollama error: {response.status_code}")

    full_response = response.json().get("response", "")
    logger.info(f"Ollama response: {full_response}\n\n")

    # Try multiple patterns to extract PromQL
    match = re.search(PROMQL_PATTERN, full_response, re.DOTALL)
    
    if not match:
        # Pattern: ```<optional_language>\n<query>\n```
        match = re.search(r"```(?:\w+)?\s*\n(.*?)\n\s*```", full_response, re.DOTALL)
    
    if not match:
        # Pattern without newlines: ```<optional_language><query>```
        match = re.search(r"```(?:\w+)?\s*(.*?)\s*```", full_response, re.DOTALL)
    
    if not match:
        # Try to find query between "query:" and newline or end
        match = re.search(r"query:\s*([^\n]+)", full_response, re.IGNORECASE)
    
    if not match:
        # Last resort: look for common PromQL patterns (functions with metrics)
        match = re.search(r"((?:sum|avg|min|max|count|rate|increase|avg_over_time|sum_over_time|max_over_time|min_over_time)\s*\([^)]+\)(?:\s*(?:by|without)\s*\([^)]*\))?)", full_response, re.IGNORECASE)
    
    if not match:
        logger.error(f"Ollama response did not contain a valid PromQL query. Full response:\n{full_response}")
        raise ValueError(f"No valid PromQL found in response. Response length: {len(full_response)} chars")

    promql = match.group(1).strip()
    
    # Clean up language identifiers that might have been captured
    promql = re.sub(r'^(promql|markdown|sql|python|bash)\s*\n', '', promql, flags=re.IGNORECASE)
    
    # Remove comments (# and everything after on the same line)
    promql = re.sub(r'#.*', '', promql)
    
    # Clean up any square brackets or placeholder text that might have been included
    promql = re.sub(r'^\s*\[\s*', '', promql)  # Remove leading [
    promql = re.sub(r'\s*\]\s*$', '', promql)  # Remove trailing ]
    promql = promql.strip()
    
    # Basic validation to catch common issues
    if not promql:
        logger.error("Extracted PromQL is empty")
        raise ValueError("Empty PromQL query")
    
    # Check for common syntax errors
    syntax_issues = []
    
    # Check for conflicting 'by' and 'without' modifiers
    if re.search(r'\b(by|without)\s*\([^)]*\)\s*(by|without)\s*\(', promql, re.IGNORECASE):
        syntax_issues.append("cannot use both 'by' and 'without' modifiers together")
    
    # Check for aggregation operators with incorrect syntax
    aggregation_ops = ['sum', 'min', 'max', 'avg', 'count', 'stddev', 'stdvar', 'count_values', 'bottomk', 'topk', 'quantile']
    for op in aggregation_ops:
        # Pattern: aggregation operator followed by 'over' (incorrect)
        if re.search(rf'\b{op}\s+over\s*\(', promql, re.IGNORECASE):
            syntax_issues.append(f"'{op} over' detected - use '{op} by' or '{op} without' instead")
            break
        # Pattern: aggregation operator with grouping that doesn't use 'by' or 'without'
        if re.search(rf'\b{op}\s+\w+\s*\(', promql, re.IGNORECASE):
            # Check if it's not followed by 'by' or 'without'
            if not re.search(rf'\b{op}\s+(by|without)\s*\(', promql, re.IGNORECASE):
                match = re.search(rf'\b{op}\s+(\w+)\s*\(', promql, re.IGNORECASE)
                if match and match.group(1).lower() not in ['by', 'without']:
                    syntax_issues.append(f"aggregation operator '{op}' should be followed by 'by' or 'without', not '{match.group(1)}'")
                    break
    
    if promql.count('(') != promql.count(')'):
        syntax_issues.append("unbalanced parentheses")
    
    if promql.count('[') != promql.count(']'):
        syntax_issues.append("unbalanced square brackets")
    
    if promql.count('{') != promql.count('}'):
        syntax_issues.append("unbalanced curly braces")
    
    # Check for incomplete range vectors
    if '[' in promql and not re.search(r'\[\d+[smhdwy]\]', promql):
        syntax_issues.append("potentially incomplete or invalid time range specification")
    
    # Check for range vectors used directly in aggregations (common error)
    # Pattern: aggregation(metric[time]) - should be aggregation(function(metric[time]))
    if re.search(r'\b(' + '|'.join(aggregation_ops) + r')\s*(?:by|without)?\s*\([^)]*\[[0-9]+[smhdwy]\]\s*\)', promql, re.IGNORECASE):
        syntax_issues.append("range vector used directly in aggregation - wrap with rate(), avg_over_time(), or similar function first")
    
    # Check for over-time functions missing time ranges
    over_time_funcs = ['avg_over_time', 'sum_over_time', 'min_over_time', 'max_over_time', 
                       'count_over_time', 'stddev_over_time', 'stdvar_over_time', 'last_over_time',
                       'present_over_time', 'quantile_over_time']
    for func in over_time_funcs:
        # Check if function is used but NOT followed by a range vector
        if re.search(rf'\b{func}\s*\([^)]*\)', promql, re.IGNORECASE):
            # Check if there's NO time range inside
            if not re.search(rf'\b{func}\s*\([^)]*\[[0-9]+[smhdwy]\]', promql, re.IGNORECASE):
                syntax_issues.append(f"'{func}' requires a range vector (e.g., metric[5m]) as argument")
                break
    
    if syntax_issues:
        logger.warning(f"Potential syntax issues detected in PromQL: {', '.join(syntax_issues)}")
    
    logger.info(f"Extracted PromQL: {promql}")
    return promql, full_response

# STEP 2: Run PromQL on Prometheus
def query_prometheus(promql: str, prom_config: dict):
    logger.info(f"Querying Prometheus with: {promql}")
    # Handle both direct config and prometheus_instances structure
    if "prometheus_instances" in prom_config:
        # Extract first instance from list
        instance = prom_config["prometheus_instances"][0]
        base_url = instance["base_url"]
        disable_ssl = instance.get("disable_ssl", False)
    else:
        # Fallback logic: check for 'base_url', then 'prometheus_url', then 'url'
        base_url = prom_config.get("base_url") or \
                   prom_config.get("prometheus_url") or \
                   prom_config.get("url")
        disable_ssl = prom_config.get("disable_ssl", True)
    
    prom = PrometheusConnect(
        url=base_url,
        disable_ssl=disable_ssl
    )

    try:
        result = prom.custom_query(query=promql)
        logger.info("Prometheus query successful")
        return {
            "promql": promql,
            "result": result
        }
    except Exception as e:
        logger.error(f"Prometheus query failed: {e}")
        return {
            "promql": promql,
            "error": str(e)
        }

# STEP 3: Send PromQL results back to Ollama for final answer
def get_final_answer_from_ollama(user_question: str, promql: str, prom_result: dict) -> str:
    system_prompt = """You are an expert copilot for Prometheus metric data. Your task is to analyze Prometheus query results and provide a clear, concise answer to the user's question.

The user asked a question, we generated a PromQL query to get the data, and now you need to interpret the results to answer their original question.

Focus on:
- Directly answering the user's question based on the data
- Extracting relevant insights from the Prometheus results for the user's question
- Explaining what the metrics show in plain language
- Being concise

If there's an error or no data, explain what that means in context of their question."""

    # Format the prompt with the user question, PromQL, and results
    if "error" in prom_result:
        data_section = f"Error occurred while querying Prometheus: {prom_result['error']}"
    else:
        data_section = f"Prometheus returned the following data: {prom_result['result']}"
    
    final_prompt = f"""{system_prompt}

User's original question: {user_question}

PromQL query used: {promql}

{data_section}

Please provide a clear answer to the user's question based on this information:"""

    logger.info(f"Sending final analysis request to Ollama. User question: '{user_question}'. Prompt (truncated): '{final_prompt[:100]}...'")

    try:
        response = httpx.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": final_prompt,
            "stream": False
        }, timeout=120)
    except Exception as e:
        logger.error(f"Failed to connect to Ollama for final answer: {e}")
        raise

    if response.status_code != 200:
        logger.error(f"Ollama failed for final answer: {response.status_code} - {response.text}")
        raise RuntimeError(f"Ollama error: {response.status_code}")

    final_answer = response.json().get("response", "")
    logger.info("Final answer generated successfully")
    return final_answer

# MAIN ENTRY POINT
def run(question: str, prom_config: dict):
    try:
        promql, ollama_response = get_promql_from_ollama(question)
        result = query_prometheus(promql, prom_config)
        final_answer = get_final_answer_from_ollama(question, promql, result)
        
        result["ollama_response"] = ollama_response
        result["final_answer"] = final_answer
        return result
    except Exception as e:
        logger.exception("Error in copilot HTTP logic")
        return {"error": str(e)}
